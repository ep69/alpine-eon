#!/usr/bin/python3

import os
import smbus
import click

FILE_FANSPEED = "/tmp/eon-fanspeed"  # file to store fan speed

# For each fan speed, range of temperatures that are ok
SPEED_TEMP_HDD = {
    0: (None, 43),
    25: (40, 47),
    60: (43, 50),
    100: (47, None),
}
SPEED_TEMP_CPU = {
    0: (None, 45),
    25: (40, 50),
    60: (45, 55),
    100: (50, None),
}


def temp_to_speed(ctemp, speed_temp_ranges, oldspeed=None):
    def is_in_range(n, low, high):
        if (low is None or n >= low) and (high is None or n <= high):
            return True

        return False

    newspeed = None
    for speed, limits in sorted(speed_temp_ranges.items()):
        if is_in_range(ctemp, limits[0], limits[1]):
            if newspeed is None:  # prefer lower speed if already found
                newspeed = speed
            if speed == oldspeed:  # no change is needed, break immediately
                newspeed = speed
                break

    assert newspeed is not None  # wrong speed_temp_ranges specification?

    return newspeed


def adjusted_speed(temps, ranges_list, oldspeed=None):
    assert len(temps) == len(ranges_list)
    assert len(temps) >= 1

    speeds = []
    for i in range(len(temps)):
        speeds.append(temp_to_speed(temps[i], ranges_list[i], oldspeed))

    return max(speeds)


def get_fan_speed():
    speed = None
    try:
        with open(FILE_FANSPEED, "r") as f:
            content = f.read()
        speed = int(content.strip())
        speed = max(0, min(100, speed))
    except (FileNotFoundError, ValueError):
        speed = -1
    return speed


def set_fan_speed(speed):
    speed = int(speed)
    speed = max(0, min(100, speed))
    bus = smbus.SMBus(1)
    bus.write_byte(0x1A, speed)
    with open(FILE_FANSPEED, "w") as f:
        f.write(f"{speed}\n")


def get_temp_hdd():
    DISK = "/dev/disk/by-uuid/7fbe4649-c137-4489-b74e-c267053e2579"
    cmd = f"/usr/sbin/smartctl -d sat -A {DISK} |grep Temperature_Celsius |awk '{{print $10}}'"

    temp = -1
    output = os.popen(cmd + " 2>&1").read()
    temp = int(output)

    return temp


def get_temp_cpu():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        content = f.readline().strip()
    return int(content) // 1000


@click.group(invoke_without_command=True)
@click.option(
    "--dry-run",
    is_flag=True,
    show_default=True,
    default=False,
    help="Do not actually change anything",
)
@click.pass_context
def main(ctx, dry_run):
    ctx.ensure_object(dict)
    ctx.obj["dryrun"] = dry_run
    if ctx.invoked_subcommand is None:
        info()


@main.command(short_help="Print information (default)")
def info():
    temp_hdd = get_temp_hdd()
    print(f"Temperature (disk): {temp_hdd}")
    temp_cpu = get_temp_cpu()
    print(f"Temperature (cpu): {temp_cpu}")

    fanspeed = get_fan_speed()
    print(f"Fan speed: {fanspeed}")


@main.command(short_help="Adjust fan speed based on temperature")
@click.pass_context
def adjust(ctx):
    temp_hdd = get_temp_hdd()
    temp_cpu = get_temp_cpu()
    oldspeed = get_fan_speed()
    newspeed = adjusted_speed(
        [temp_hdd, temp_cpu], [SPEED_TEMP_HDD, SPEED_TEMP_CPU], oldspeed
    )
    if newspeed == oldspeed:
        print(f"No adjust needed, already on {newspeed}")
        return
    if ctx.obj["dryrun"]:
        print(f"Dry run, would adjust {oldspeed}->{newspeed}")
    else:
        set_fan_speed(newspeed)


@main.command(short_help="Set fan speed (0-100)")
@click.argument("speed", type=click.IntRange(min=0, max=100))
@click.pass_context
def fan(ctx, speed):
    if ctx.obj["dryrun"]:
        print(f"Dry run, would set {speed}")
    else:
        set_fan_speed(speed)


@main.command(short_help="Check dependencies")
def check():
    cmd = "which smartctl"

    with os.popen(cmd) as f:
        output = f.read().strip()

    good = True

    if output != "/usr/sbin/smartctl":
        print(
            f"Error: smartctl not found, please install 'smartmontools' package ({output})"
        )
        good = False

    if good:
        print("All good!")
        return 0
    else:
        print("Fixes needed")
        return 1


if __name__ == "__main__":
    main()

# TODO:
#  * shutdown
#  * loading config ranges
#  * display
