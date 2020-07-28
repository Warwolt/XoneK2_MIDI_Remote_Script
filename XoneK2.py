import time
from functools import partial

# Script imports
import Live
import MidiRemoteScript
from _Framework.ButtonElement import ButtonElement
from _Framework.ButtonMatrixElement import ButtonMatrixElement
from _Framework.ControlSurface import ControlSurface
from _Framework.DeviceComponent import DeviceComponent
from _Framework.EncoderElement import EncoderElement
from _Framework.InputControlElement import *
from _Framework.MixerComponent import MixerComponent
from _Framework.SessionComponent import SessionComponent
from _Framework.SliderElement import SliderElement
from _Framework.TransportComponent import TransportComponent

# Debugging imports
import DebugPrint
import inspect

# The Xone K2 uses midi channel 15 (zero indexed gives 14)
MIDI_CHANNEL_NUM = 15 -1

def Button(note_num, name=None):
    rv = ButtonElement(True, MIDI_NOTE_TYPE, MIDI_CHANNEL_NUM, note_num)
    if name is not None:
        rv.name = name
    return rv


def Fader(note_num):
    return SliderElement(MIDI_CC_TYPE, MIDI_CHANNEL_NUM, note_num)


def Knob(cc):
    return EncoderElement(MIDI_CC_TYPE, MIDI_CHANNEL_NUM, cc,
        Live.MidiMap.MapMode.absolute)


def Encoder(cc):
    return EncoderElement(MIDI_CC_TYPE, MIDI_CHANNEL_NUM, cc,
        Live.MidiMap.MapMode.absolute)


class XoneK2(ControlSurface):
    def __init__(self, c_instance):
        super(XoneK2, self).__init__(c_instance, False)
        DebugPrint.log_message("XoneK2 constructor called")

        with self.component_guard():
            self._set_suppress_rebuild_requests(True)

            # experiment to light up LAYER button red
            # https://www.allen-heath.com/media/XoneK2_UG_AP8509_3.pdf
            status = MIDI_NOTE_ON_STATUS + MIDI_CHANNEL_NUM
            MIDI_NOTE_C0 = 0x0C
            velocity = 127
            c_instance.send_midi((status, MIDI_NOTE_C0, velocity))

            # self.init_session()
            # self.init_mixer()
            # self.init_matrix()
            # self.init_tempo()

            # # connect mixer to session
            # self.session.set_mixer(self.mixer)
            # self.session.update()
            # self.set_highlighting_session_component(self.session)
            # self._set_suppress_rebuild_requests(False)

