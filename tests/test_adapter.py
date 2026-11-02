import time
import unittest
from types import SimpleNamespace
from adapter.main import AXES, MASK, Controller

class Fake:
    JOG_STOP=0
    JOG_CONTINUOUS=1
    STATE_ESTOP=1
    STATE_ESTOP_RESET=2
    STATE_OFF=3
    STATE_ON=4
    MODE_MANUAL=1
    INTERP_IDLE=1
    TRAJ_MODE_TELEOP=3
    def __init__(self):
        self.calls=[]
        self.s=SimpleNamespace(axis_mask=MASK, joints=4, estop=False, enabled=True,
            homed=[1]*4, motion_mode=3, task_mode=1, interp_state=1,
            actual_position=[10,20,0,0,0,0,60,70,0],
            joint_actual_position=[10,20,60,70],
            g5x_offset=[1,2,0,0,0,0,6,7,0], tool_offset=[0]*9,
            g92_offset=[0]*9, rotation_xy=0, paused=False, motion_line=1,
            file="", poll=lambda: None)
    def stat(self): return self.s
    def command(self): return self
    def error_channel(self): return SimpleNamespace(poll=lambda: None)
    def jog(self,*args): self.calls.append(args)

class Tests(unittest.TestCase):
    def setUp(self):
        self.api=Fake()
        self.c=Controller(self.api, ".")
    def test_uv_use_coordinate_indices(self):
        result=self.c.snapshot()
        self.assertEqual(result["work"], {"X":9,"Y":18,"U":54,"V":63})
        self.c.execute({"cmd":"jog","axis":"U","velocity":1,"session":"a"})
        self.assertEqual(self.api.calls[-1], (1,False,6,1))
    def test_lease_expires_stops_all_four_axes(self):
        self.c.execute({"cmd":"jog","axis":"V","velocity":1,"session":"a"})
        self.c.deadline=time.monotonic()-1
        self.c.expire()
        self.assertEqual([v[2] for v in self.api.calls[-4:]], [0,1,6,7])
        self.assertIsNone(self.c.owner)
    def test_other_session_cannot_take_jog(self):
        self.c.execute({"cmd":"jog","axis":"X","velocity":1,"session":"a"})
        with self.assertRaises(ValueError):
            self.c.execute({"cmd":"jog","axis":"U","velocity":1,"session":"b"})
    def test_wrong_geometry_and_nonfinite_velocity_rejected(self):
        for velocity in (float("nan"),float("inf"),True,6):
            with self.assertRaises(ValueError):
                self.c.execute({"cmd":"jog","axis":"X","velocity":velocity,"session":"a"})
        self.api.s.axis_mask=7
        with self.assertRaises(ValueError): self.c.snapshot()
    def test_stop_attempts_remaining_axes_after_failure(self):
        attempted=[]
        def failing_jog(*args):
            attempted.append(args[2])
            if args[2] == 0:
                raise RuntimeError("lost axis")
        self.api.jog=failing_jog
        with self.assertRaises(RuntimeError): self.c.stop()
        self.assertEqual(attempted, [0,1,6,7])
        self.assertIsNone(self.c.owner)
    def test_joint_mode_rejected(self):
        self.api.s.motion_mode=1
        with self.assertRaises(ValueError):
            self.c.execute({"cmd":"jog","axis":"U","velocity":1,"session":"a"})
if __name__ == "__main__": unittest.main()
