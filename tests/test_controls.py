import unittest
from test_adapter import Fake
from adapter.main import Controller

class ControlFake(Fake):
    MODE_MDI=3
    def __init__(self):
        super().__init__()
        self.serial=0
        self.s.echo_serial_number=0
    def state(self,value):self.calls.append(("state",value))
    def mode(self,value):self.calls.append(("mode",value))
    def mdi(self,text):
        self.serial+=1
        self.calls.append(("mdi",text))
    def abort(self):self.calls.append(("abort",))

class ControlsTests(unittest.TestCase):
    def setUp(self):
        self.api=ControlFake()
        self.c=Controller(self.api,".")
    def send(self,cmd,**extra):
        return self.c.execute({"cmd":cmd,"session":"test",**extra})
    def test_mdi_requires_mode_and_all_four_homed(self):
        with self.assertRaises(ValueError):self.send("mdi",text="G90")
        self.api.s.homed=[1,1,0,0]
        with self.assertRaises(ValueError):self.send("mdi_mode")
        self.api.s.homed=[1]*4
        self.send("mdi_mode")
        self.assertEqual(self.api.calls[-1],("mode",3))
        self.api.s.task_mode=3
        self.send("mdi",text="G90")
        self.assertEqual(self.api.calls[-1],("mdi","G90"))
        with self.assertRaises(ValueError):self.send("mdi",text="G91")
        self.api.s.echo_serial_number=self.api.serial
        self.send("mdi",text="G91")
    def test_mdi_rejects_bad_states_and_multiple_lines(self):
        self.api.s.task_mode=3
        for text in ("","G90\nG0 X1","G90\x00","X"*255):
            with self.assertRaises(ValueError):self.send("mdi",text=text)
        for attr,value in (("estop",True),("enabled",False),("paused",True),("interp_state",2)):
            old=getattr(self.api.s,attr)
            setattr(self.api.s,attr,value)
            with self.assertRaises(ValueError):self.send("mdi",text="G90")
            setattr(self.api.s,attr,old)
    def test_estop_and_disable_survive_failed_jog_stop(self):
        def fail(*args):raise RuntimeError("Jog stop unavailable")
        self.api.jog=fail
        self.send("estop")
        self.assertIn(("state",self.api.STATE_ESTOP),self.api.calls)
        self.send("disable")
        self.assertIn(("state",self.api.STATE_OFF),self.api.calls)

if __name__=="__main__":unittest.main()
