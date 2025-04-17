"""
Guest boot sanity test with passthrough device in different mode
- Apic, X2apic, Avic, X2avic
"""

import os
from avocado.utils import process, pci, linux_modules, genio
from virttest import env_process


def run(test, params, env):  # pylint: disable=R0915
    """
    Guest boot sanity test with passthrough device in different modes
    - Apic, X2apic, Avic, X2avic
    """
    login_timeout = int(params.get("login_timeout", 240))
    pci_device = params.get("pci_device", "")
    session = None

    try:

        def configure_module(module, config):
            """
            Check if 'config' is not set, builtin or module.
            Load 'module' if 'config' is set as module.
            Cancel test if 'config' is not set.
            """
            config_status = linux_modules.check_kernel_config(config)
            if config_status == linux_modules.ModuleConfig.NOT_SET:
                test.cancel(f"{config} is not set. Cancelling the test")
            elif config_status == linux_modules.ModuleConfig.MODULE:
                test.log.debug(f"{config} is set as a module.")
                if linux_modules.load_module(module):
                    if linux_modules.module_is_loaded(module):
                        test.log.debug(f"Module {module} loaded successfully")
                    else:
                        test.cancel(f"Module {module} loading failed")
            elif config_status == linux_modules.ModuleConfig.BUILTIN:
                test.log.debug(f"{config} is built-in.")

        def check_avic_support():
            """
            Check if system supports avic.
            """
            cmd = "rdmsr -p 0 0xc00110dd --bitfield 13:13"
            out = process.run(cmd, sudo=True, shell=True).stdout_text.strip()
            if out == "0":
                test.cancel("System doesnot support avic")

        def check_x2avic_support():
            """
            check if system supports x2avic.
            """
            cmd = "rdmsr -p 0 0xc00110dd --bitfield 18:18"
            out = process.run(cmd, sudo=True, shell=True).stdout_text.strip()
            if out == "0":
                test.cancel("System doesnot support x2avic")

        # Check system support for avic or x2avic
        if params["kvm_probe_module_parameters"] == "avic=1":
            configure_module("msr", "CONFIG_X86_MSR")
            if params["mode"] == "apic":
                check_avic_support()
            if params["mode"] == "x2apic":
                check_x2avic_support()

        params["start_vm"] = "yes"
        vm = env.get_vm(params["main_vm"])
        env_process.preprocess_vm(test, params, env, params.get("main_vm"))
        session = vm.wait_for_login(timeout=login_timeout)
        vm.verify_kernel_crash()

        def attach_vfio_pci_driver(device):
            """
            Unbind device from attached driver and bind it to vfio-pci driver.

            :param device: pci device
            """

            test.log.debug(f"Attaching vfio-pci driver to device {device}")

            if not os.path.exists("/sys/bus/pci/drivers/vfio-pci"):
                test.cancel("vfio-pci module not found")

            # Get vendor id of pci device
            output = pci.get_vendor_id(device)
            cmd = f"echo {output} | sed 's/:/ /g'"
            vid = process.run(cmd, sudo=True, shell=True).stdout_text.strip()

            # Add pci_addr vendor id to vfio-pci driver
            cmd = f"echo {vid} > /sys/bus/pci/drivers/vfio-pci/new_id"
            process.run(cmd, ignore_status=True, shell=True, sudo=True)

            # unbind the device from its driver
            driver = pci.get_driver(device)
            if driver is not None:
                pci.unbind(driver, device)

            # Bind device to vfio-pci driver
            pci.bind("vfio-pci", device)

        def check_passthrough_requirements():
            """
            Validate IOMMU, Interrupt Remapping, and vfio-pci module availability
            """

            # Check if interrupt remapping is enabled on system
            out = process.run("dmesg", ignore_status=True, verbose=False, sudo=True)
            for line in out.stdout_text.split("\n"):
                if "AMD-Vi: Interrupt remapping enabled" in line:
                    break
                if line == out.stdout_text.split("\n")[-1]:
                    test.cancel("IOMMU interrupt remaping is not enabled")

            # Check and load vfio-pci module
            configure_module("vfio-pci", "CONFIG_VFIO_PCI")

        # Passthrough device/s and validate if passthrough is successful
        if pci_device != "":
            # Perform pre-checks and prereq enablements before pci passthrough
            check_passthrough_requirements()

            # Capture number of pci devices in guest before pci passthrough
            num_pcidev_before = session.cmd_output(
                "ls /sys/bus/pci/devices/ | wc -l"
            ).strip()

            # Perform pci passthrough
            for i in range(len(pci_device.split(" "))):
                attach_vfio_pci_driver(pci_device.split(" ")[i])
                params[
                    "extra_params"
                ] += f" -device vfio-pci,host={pci_device.split(' ')[i]}"
            env_process.preprocess_vm(test, params, env, params.get("main_vm"))
            session = vm.wait_for_login(timeout=login_timeout)

            # Capture number of pci devices in guest after pci passthrough
            num_pcidev_after = session.cmd_output(
                "ls /sys/bus/pci/devices/ | wc -l"
            ).strip()

            # Validate if pci passthrough is successful
            if int(num_pcidev_after) != int(num_pcidev_before) + len(
                pci_device.split(" ")
            ):
                test.fail("PCI device/s passthrough is not successful")
            else:
                test.log.debug("PCI device/s passthrough is successful")

        # Collect guest system details
        test.log.debug(f"Debug: {session.cmd_output('cat /etc/os-release')}")
        test.log.debug(f"Debug: {session.cmd_output('uname -a')}")
        test.log.debug(f"Debug: {session.cmd_output('ls /boot/')}")
        test.log.debug(f"Debug: {session.cmd_output('lspci -k')}")
        test.log.debug(f"Debug: {session.cmd_output('lscpu')}")
        test.log.debug(f"Debug: {session.cmd_output('lsblk')}")
        test.log.debug(f"Debug: {session.cmd_output('df -h')}")
        test.log.debug(f"Debug: {session.cmd_output('ping -c 2 google.com')}")
        test.log.debug(f"Debug: {session.cmd_output('dmesg')}")

    finally:
        if session:
            session.close()
        vm.destroy()
