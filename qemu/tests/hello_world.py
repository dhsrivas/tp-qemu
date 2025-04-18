import time

from avocado.utils import process
from virttest import error_context


# This decorator makes the test function aware of context strings
@error_context.context_aware
def run(test, params, env):
    """
    QEMU 'Hello, world!' test

    1) Boot the main vm, or just grab it if it's already booted.
    2) Echo "Hello, world!" in guest and get the output.
    3) Compare whether the return matches our expectations.
    4) Send a monitor command and log its output.
    5) Verify whether the vm is running through monitor.
    6) Echo "Hello, world!" in the host using shell.
    7) Compare whether the return matches our expectations.
    8) Get a sleep_time parameter from the config file and sleep
       during the specified sleep_time.

    This is a sample QEMU test, so people can get used to some of the test APIs.

    :param test: QEMU test object.
    :param params: Dictionary with the test parameters.
    :param env: Dictionary with test environment.
    """
    # Error contexts are used to give more info on what was
    # going on when one exception happened executing test code.
    error_context.context("Get the main VM", test.log.info)
    vm = env.get_vm(params["main_vm"])
    vm.verify_alive()

    # Each test has a params dict, with lots of
    # key = value pairs. Values are always strings
    # In this case, we'll convert login_timeout to int
    timeout = int(params.get("login_timeout", 360))
    # This represents an SSH session. You can end it calling
    # session.close(), but you don't need to since the framework
    # takes care of closing all sessions that were opened by a test.
    session = vm.wait_for_login(timeout=timeout)

    # Send command to the guest, using session command.
    error_context.context(
        "Echo 'Hello, world!' in guest and get the output", test.log.info
    )
    # Here, timeout was passed explicitly to show it can be tweaked
    guest_cmd = "echo 'Hello, world!'"
    # If you just need the output, use session.cmd(). If the command fails,
    # it will raise a aexpect.ShellCmdError exception
    guest_cmd_output = session.cmd(guest_cmd, timeout=60)
    # The output will contain a newline, so strip()
    # it for the purposes of pretty printing and comparison
    guest_cmd_output = guest_cmd_output.strip()
    test.log.info("Guest cmd output: '%s'", guest_cmd_output)

    # Here, we will fail a test if the guest outputs something unexpected
    if guest_cmd_output != "Hello, world!":
        test.fail("Unexpected output from guest")

    # Send command to the guest, using monitor command.
    error_context.context("Send a monitor command", test.log.info)

    monitor_cmd_ouput = vm.monitor.info("status")
    test.log.info("Monitor returns '%s'", monitor_cmd_ouput)

    # Verify whether the VM is running. This will throw an exception in case
    # it is not running, failing the test as well.
    vm.verify_status("running")

    # Send command to host
    error_context.context("Echo 'Hello, world!' in the host using shell", test.log.info)
    # If the command fails, it will raise a process.CmdError exception
    host_cmd_output = process.system_output("echo 'Hello, world!'", shell=True).decode()
    test.log.info("Host cmd output '%s'", host_cmd_output)

    # Here, we will fail a test if the host outputs something unexpected
    if host_cmd_output != "Hello, world!":
        test.fail("Unexpected output from guest")

    # An example of getting a required parameter from the config file
    error_context.context(
        "Get a required parameter from the config file", test.log.info
    )
    sleep_time = int(params["sleep_time"])
    test.log.info("Sleep for '%d' seconds", sleep_time)
    time.sleep(sleep_time)
