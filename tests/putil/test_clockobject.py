import time
import sys

# Epsilon for taking floating point calculation inaccuracies in mind
EPSILON = 1e-06

# We must account for clock inaccuracy
if sys.platform == 'win32' or sys.platform == 'cygwin':
    # Assume 19 milliseconds inaccuracy on Windows (worst case)
    # 16 milliseconds plus 3 milliseconds for execution time
    CLOCK_INACCURACY = 0.019
else:
    # On other platforms, assume 5 milliseconds, allowing for execution time
    # (5000 times higher than their actual 1 microsecond accuracy)
    CLOCK_INACCURACY = 0.005


def test_clock_get_frame_time(clockobj):
    current_time = clockobj.get_frame_time()
    time.sleep(0.2)
    assert clockobj.get_frame_time() == current_time


def test_clock_jump_frame_time(clockobj):
    current_time = clockobj.get_frame_time()
    clockobj.tick()
    assert clockobj.get_frame_time() == current_time + clockobj.get_frame_time()


def test_clock_get_real_time(clockobj):
    current_time = clockobj.get_real_time()
    time.sleep(0.4)
    assert clockobj.get_real_time() - current_time + EPSILON >= 0.4 - CLOCK_INACCURACY


def test_clock_get_long_time(clockobj):
    current_time = clockobj.get_long_time()
    time.sleep(0.4)
    assert clockobj.get_long_time() - current_time + EPSILON >= 0.4 - CLOCK_INACCURACY


def test_clock_get_dt(clockobj):
    clockobj.tick()
    first_tick = clockobj.get_frame_time()
    clockobj.tick()
    second_tick = clockobj.get_frame_time()
    assert clockobj.get_dt() == second_tick - first_tick


def test_clock_copy_keeps_forced_time(clockobj):
    # The frame time of a forced clock is reckoned from an epoch, which a copy
    # of its cycled data must keep: the pipeline copies it every frame when
    # it is threaded.
    from panda3d.core import ClockObject

    clockobj.set_mode(ClockObject.M_forced)
    clockobj.set_frame_rate(1000)
    clockobj.set_frame_time(5.0)
    copy = ClockObject(clockobj)
    clockobj.tick()
    copy.tick()
    assert abs(copy.get_frame_time() - clockobj.get_frame_time()) < EPSILON
    assert abs(clockobj.get_frame_time() - 5.001) < EPSILON


def test_clock_reset(clockobj):
    clockobj.reset()
    assert clockobj.get_dt() == 0
    assert clockobj.get_frame_time() == 0
    assert clockobj.get_real_time() - EPSILON <= CLOCK_INACCURACY
