"""
Guest boot sanity test with passthrough device in different mode
- Apic, X2apic, Avic, X2avic
"""

from avocado.utils.software_manager.manager import SoftwareManager
from avocado.utils import process, pci, linux_modules
from virttest import data_dir, env_process
import os


def run(test, params, env):
    """
    Guest boot sanity test with passthrough device in different mode
    - Apic, X2apic, Avic, X2avic
    """
    iterations = int(params.get("iterations", "1"))
    login_timeout = int(params.get("login_timeout", 360))
    kernel_version = params.get("kernel_version", "")
    device_type = params.get("libvirt_pci_device_type", "NONE")
    pci_device = params.get("pci_device", "")

    vm = env.get_vm(params["main_vm"])

    # Boot guest with custom kernel
    if kernel_version != "":
        install_path = data_dir.get_data_dir()
        process.system("cp /boot/vmlinuz-%s %s" % (kernel_version, install_path))
        process.system("cp /boot/initrd.img-%s %s" % (kernel_version, install_path))
        kernel_path = install_path + ("/vmlinuz-%s" % kernel_version)
        initrd_path = install_path + ("/initrd.img-%s" % kernel_version)
        params["kernel"] = kernel_path
        params["initrd"] = initrd_path
        params["kernel_params"] = (
            "ro net.ifnames=0 biosdevname=0 console=tty0 console=ttyS0 earlyprintk=serial root=/dev/vda biosdevname=0 movable_node swiotlb=65536"
        )

    env_process.preprocess_vm(test, params, env, params.get("main_vm"))
    session = vm.wait_for_login(timeout=login_timeout)
    vm.verify_kernel_crash()

    # Validate if booted with correct kernel
    if kernel_version != "":
        if kernel_version != session.cmd_output("uname -r").strip():
            test.fail(
                "Guest not booted with passed kernel version %s"
                % session.cmd_output("uname -r")
            )
        else:
            test.log.debug("Guest booted with passed kernel version")

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
        result = process.run(cmd, ignore_status=True, shell=True, sudo=True)

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
        config_check = linux_modules.check_kernel_config("CONFIG_VFIO_PCI")
        if config_check == linux_modules.ModuleConfig.NOT_SET:
            test.cancel("Config CONFIG_VFIO_PCI is not set")
        elif config_check == linux_modules.ModuleConfig.MODULE:
            if linux_modules.load_module("vfio-pci"):
                if linux_modules.module_is_loaded("vfio-pci"):
                    test.log.debug("Module vfio-pci Loaded Successfully")
                else:
                    test.cancel("Module vfio-pci Loading Failed")
        else:
            test.log.debug("Module vfio-pci is Built In")

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
        session = vm.wait_for_login()

        # Capture number of pci devices in guest after pci passthrough
        num_pcidev_after = session.cmd_output(
            "ls /sys/bus/pci/devices/ | wc -l"
        ).strip()

        # Validate if pci passthrough is successful
        if int(num_pcidev_after) != int(num_pcidev_before) + len(pci_device.split(" ")):
            test.fail("PCI device/s passthrough is not successful")
        else:
            test.log.debug("PCI device/s passthrough is successful")

    try:
        for itr in range(iterations):
            test.log.info("Currently executing iteration number: '%s'", itr)
            session = vm.wait_for_login()
            # Collect guest system details
            test.log.debug("Debug: %s" % session.cmd_output("cat /etc/os-release"))
            test.log.debug("Debug: %s" % session.cmd_output("uname -a"))
            test.log.debug("Debug: %s" % session.cmd_output("ls /boot/"))
            test.log.debug("Debug: %s" % session.cmd_output("lspci -k"))
            test.log.debug("Debug: %s" % session.cmd_output("lscpu"))
            test.log.debug("Debug: %s" % session.cmd_output("lsblk"))
            test.log.debug("Debug: %s" % session.cmd_output("df -h"))
            test.log.debug("Debug: %s" % session.cmd_output("ping -c 2 google.com"))
            test.log.debug("Debug: %s" % session.cmd_output("dmesg"))

    #            if device_type == NONE:
    #
    #            if device_type == STORAGE:
    #
    #            if device_type == NIC:
    #
    #            if device_type == BOTH:
    #
    #            if device_type == ALL:
    finally:
        if session:
            session.close()
