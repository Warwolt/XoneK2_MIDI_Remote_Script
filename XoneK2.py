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
MIDI_CHANNEL_NUM = 15 - 1

class XoneK2(ControlSurface):
    """
    The top level class of the script that extends the ControlSurface class,
    and is returned from create_instance in the init file.
    """
    def __init__(self, c_instance):
        super(XoneK2, self).__init__(c_instance, False)
        DebugPrint.log_message("XoneK2 constructor called")

        with self.component_guard():
            self._set_suppress_rebuild_requests(True)
            self._c_instance = c_instance
            self._note_to_midi = self._create_note_to_midi_dict()
            self._element_color_to_midi = self._create_element_color_dict()
            self.light_up_element('layer_button', 'green')


    def _create_note_to_midi_dict(self):
        """
        Create a dict for the the midi implementation table in the Xone K2
        manual, to make it easier to refer to the values of the midi notes.

        The key value pairs are e.g. ('c#1', 25) or ('g4', 67).
        """
        notes = ['c','c#','d','d#','e','f', 'f#', 'g','g#','a','a#','b']
        octaves = [str(num) for num in range(-1, 10)]
        octave_notes = [note + octave for octave in octaves for note in notes]
        return {octave_notes[i]: i for i in range(len(octave_notes))}


    def _create_element_color_dict(self):
        """
        Create a dict for looking up the midi note to send to light a
        controller element, corresponding to the table in the Xone K2 manual.
        """
        return {
            'layer_button': {
                'red': self._note_to_midi['c0'],
                'orange': self._note_to_midi['e0'],
                'green': self._note_to_midi['g#0'],
            }
        }


    def light_up_element(self, element_name, color):
        """
        Send a midi message to light up an element.

        element_color_to_midi: dict returned from _create_element_color_dict()
        element_name:          the name of the element to light up
        color:                 a string 'red', 'orange', or 'green'
        """
        status = MIDI_NOTE_ON_STATUS + MIDI_CHANNEL_NUM
        note = self._element_color_to_midi[element_name][color]
        velocity = 127
        self._c_instance.send_midi((status, note, velocity))


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
