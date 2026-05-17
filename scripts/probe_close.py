import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sw

TARGET = r"D:\ClaudeProjects\TS2\models\working\testpart.SLDPRT"


def lock_path(target):
    d, base = os.path.split(target)
    return os.path.join(d, "~$" + base)


def show_lock_state(target, label):
    lp = lock_path(target)
    exists = os.path.isfile(lp)
    print(f"  {label}: lock file {'PRESENT' if exists else 'absent'}: {lp}")
    return exists


def main():
    sw = _sw.connect()
    print(f"Connected. SolidWorks {_sw.prop(sw, 'RevisionNumber')}\n")

    print("Step 1: state before open")
    show_lock_state(TARGET, "before")

    print("\nStep 2: opening")
    model, errors, warnings = _sw.open_part(sw, TARGET)
    if model is None:
        print(f"FAIL: OpenDoc6 returned None (errors={errors}, warnings={warnings})")
        sys.exit(1)
    title = _sw.prop(model, "GetTitle")
    print(f"  opened: title={title!r}")
    show_lock_state(TARGET, "after open")

    print("\nStep 3: closing via _sw.close()")
    _sw.close(sw, model)
    # Give SolidWorks a moment to release the lock
    for _ in range(10):
        if not os.path.isfile(lock_path(TARGET)):
            break
        time.sleep(0.1)
    show_lock_state(TARGET, "after close")

    print("\nStep 4: verifying ActiveDoc cleared")
    active = sw.ActiveDoc
    print(f"  sw.ActiveDoc = {active!r}")


if __name__ == "__main__":
    main()
