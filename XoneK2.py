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

EQ_DEVICES = {
    'Eq8': {
        'Gains': ['%i Gain A' % (index + 1) for index in range(8)]
    },
    'FilterEQ3': {
        'Gains': ['GainLo', 'GainMid', 'GainHi'],
        'Cuts': ['LowOn', 'MidOn', 'HighOn']
    }
}

# Channels are counted from 0. This is what people would normally call
# channel 15.
MIDI_CHANNEL_NUM = 14

NUM_TRACKS = 4
NUM_SCENES = 4

ENCODERS = [0, 1, 2, 3]
PUSH_ENCODERS = [52, 53, 54, 55]
KNOBS1 = [4, 5, 6, 7]
BUTTONS1 = [48, 49, 50, 51]
KNOBS2 = [8, 9, 10, 11]
BUTTONS2 = [44, 45, 46, 47]
KNOBS3 = [12, 13, 14, 15]
BUTTONS3 = [40, 41, 42, 43]
FADERS = [16, 17, 18, 19]
GRID = [
    [36, 37, 38, 39],
    [32, 33, 34, 35],
    [28, 29, 30, 31],
    [24, 25, 26, 27],
]
ENCODER_LL = 20
PUSH_ENCODER_LL = 13
ENCODER_LR = 21
PUSH_ENCODER_LR = 14
BUTTON_LL = 12
BUTTON_LR = 15


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
    def __init__(self, instance):
        super(XoneK2, self).__init__(instance, False)
        DebugPrint.log_message("XoneK2 constructor called")

        with self.component_guard():
            self._set_suppress_rebuild_requests(True)
            # self.init_session()
            # self.init_mixer()
            # self.init_matrix()
            # self.init_tempo()

            # # connect mixer to session
            # self.session.set_mixer(self.mixer)
            # self.session.update()
            # self.set_highlighting_session_component(self.session)
            # self._set_suppress_rebuild_requests(False)

