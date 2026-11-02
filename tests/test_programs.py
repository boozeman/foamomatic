import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from test_controls import ControlFake
from adapter.main import Controller
from adapter.programs import Programs, signature, execution_text

class ProgramFake(ControlFake):
    MODE_AUTO=2
    AUTO_RUN=10
    AUTO_PAUSE=11
    AUTO_RESUME=12
    def __init__(self):
        super().__init__()
        self.s.linear_units=1
        self.s.g5x_index=1
        self.s.ini_filename="/machine.ini"
    def ini(self,path):return SimpleNamespace(findall=lambda *args:[])
    def mode(self,value):
        self.serial+=1;self.calls.append(("mode",value))
    def program_open(self,path):
        self.serial+=1;self.calls.append(("open",path))
    def auto(self,*args):
        self.serial+=1;self.calls.append(("auto",*args))

class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api=ProgramFake()
        self.c=Controller(self.api,self.temp.name)
        self.c.programs=Programs(self.temp.name)
        self.identity=self.c.programs.save("G21 G90 G94 G54\nG1 X1 Y2 U6 V7 F100\nM2\n",
            signature(self.api.s),"")
    def send(self,cmd,owner="operator"):
        return self.c.execute({"cmd":cmd,"session":owner,"program_id":self.identity})
    def acknowledge(self):
        self.api.s.echo_serial_number=self.api.serial
    def prepare_open(self):
        self.send("program_prepare")
        self.acknowledge()
        self.api.s.task_mode=2
        self.send("program_open")
        self.acknowledge()
        self.api.s.file=str(self.c.programs.records[self.identity]["path"])
    def test_only_previewed_loaded_file_can_start_once(self):
        with self.assertRaises(ValueError):self.send("program_run")
        self.prepare_open()
        self.send("program_run")
        self.assertEqual(self.api.calls[-1],("auto",self.api.AUTO_RUN,0))
        with self.assertRaises(ValueError):self.send("program_run")
        self.api.s.paused=True;self.api.s.interp_state=3
        self.send("program_resume")
        self.assertEqual(self.api.calls[-1],("auto",self.api.AUTO_RESUME))
    def test_offsets_position_file_and_owner_are_checked(self):
        self.api.s.actual_position[6]+=1
        with self.assertRaises(ValueError):self.send("program_prepare")
        self.api.s.actual_position[6]-=1
        self.send("program_prepare")
        self.acknowledge();self.api.s.task_mode=2
        with self.assertRaises(ValueError):self.send("program_open",owner="another")
        self.send("program_open")
        self.acknowledge();self.api.s.file="/unrelated.ngc"
        with self.assertRaises(ValueError):self.send("program_run")
        self.api.s.file=str(self.c.programs.records[self.identity]["path"])
        self.c.programs.records[self.identity]["path"].write_text("M8\nM2\n")
        with self.assertRaises(ValueError):self.send("program_run")
        self.assertFalse(any(call[0]=="auto" for call in self.api.calls))
    def test_abort_disconnect_and_machine_off_cancel_start(self):
        for command in ("abort","release","disable","estop"):
            self.api.s.estop=False;self.api.s.enabled=True
            self.send("program_prepare")
            self.send(command)
            self.acknowledge();self.api.s.task_mode=2
            with self.assertRaises(ValueError):self.send("program_open")
    def test_requires_homing_and_completion_of_mode_change(self):
        self.api.s.homed=[1,1,0,0]
        with self.assertRaises(ValueError):self.send("program_prepare")
        self.api.s.homed=[1]*4
        self.send("program_prepare")
        with self.assertRaises(ValueError):self.send("program_open")
    def test_normalized_feed_mode_and_percent_envelope(self):
        context={"text":"%\nG93\nG1 X1 Y2 U3 V4 F2\n%\n",
                 "linear_units":1,"g5x_index":1}
        text=execution_text(context)
        self.assertTrue(text.startswith("G21 G90 G94 G17 G40 G49 G54\n"))
        self.assertIn("G93\nG1",text)
        self.assertIn("M2 (percent end)",text)
        self.assertNotIn("\n%\n",text)
if __name__=="__main__":unittest.main()
