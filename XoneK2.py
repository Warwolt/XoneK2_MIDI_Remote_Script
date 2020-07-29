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
    """
    The top level class of the script that extends the ControlSurface class,
    and is returned from create_instance in the init file.
    """
    def __init__(self, c_instance):
        super(XoneK2, self).__init__(c_instance, False)
        DebugPrint.log_message("XoneK2 constructor called")

        with self.component_guard():
            self._set_suppress_rebuild_requests(True)
            self.c_instance = c_instance
            self.song = c_instance.song()
            self.note_to_midi = self._create_note_to_midi_dict()
            self.element_color_to_midi = self._create_element_color_dict()
            self.coarse_encoder_is_pushed = False
            self.fine_encoder_pushed = False
            self.dim_all_elements()

            # Nudge buttons
            nudge_up_btn = Button(0x0F)
            nudge_back_btn = Button(0x0C)
            nudge_up_btn.add_value_listener(self.on_nudge_up)
            nudge_back_btn.add_value_listener(self.on_nudge_back)

            # Tempo encoders
            coarse_tempo_enc = Encoder(0x14)
            coarse_tempo_push = Button(0x0D)
            fine_tempo_enc = Encoder(0x15)
            fine_tempo_pushed = Button(0x0E)
            coarse_tempo_enc.add_value_listener(self.on_coarse_tempo_change)
            coarse_tempo_push.add_value_listener(self.on_coarse_encoder_push)
            fine_tempo_enc.add_value_listener(self.on_fine_tempo_change)
            fine_tempo_pushed.add_value_listener(self.on_fine_encoder_push)

    def on_nudge_back(self, value):
        """ Called when nudge back button pressed. """
        if value == 127:
            self.song.nudge_down = True
            self.light_up_element('layer_button', 'orange')
        else:
            self.song.nudge_down = False
            self.dim_element('layer_button', 'orange')

    def on_nudge_up(self, value):
        """ Called when nudge up button pressed. """
        if value == 127:
            self.song.nudge_up = True
            self.light_up_element('exit_setup_button', 'orange')
        else:
            self.song.nudge_up = False
            self.dim_element('exit_setup_button', 'orange')

    def on_coarse_tempo_change(self, value):
        """ Called when the coarse tempo encoder is rotated. """
        if value == 1:
            if self.coarse_encoder_is_pushed:
                self.song.tempo += 0.1
            else:
                self.song.tempo += 1.0
        else:
            if self.coarse_encoder_is_pushed:
                self.song.tempo -= 0.1
            else:
                self.song.tempo -= 1.0

    def on_coarse_encoder_push(self, value):
        """ Called when the coarse tempo encoder is pushed. """
        if value == 127:
            self.coarse_encoder_is_pushed = True
        else:
            self.coarse_encoder_is_pushed = False

    def on_fine_tempo_change(self, value):
        """ Called when the fine tempo encoder is rotated. """
        if value == 1:
            if self._fine_encoder_is_pushed:
                self.song.tempo += 0.01
            else:
                self.song.tempo += 0.1
        else:
            if self._fine_encoder_is_pushed:
                self.song.tempo -= 0.01
            else:
                self.song.tempo -= 0.1

    def on_fine_encoder_push(self, value):
        """ Called when the fine tempo encoder is pushed. """
        if value == 127:
            self._fine_encoder_is_pushed = True
        else:
            self._fine_encoder_is_pushed = False

    def light_up_element(self, element_name, color):
        """
        Send a midi message to light up a controller element.

        element_name: the name of the element to light up
        color:        a string 'red', 'orange', or 'green'
        """
        status = MIDI_NOTE_ON_STATUS + MIDI_CHANNEL_NUM
        note = self.element_color_to_midi[element_name][color]
        velocity = 127
        self.c_instance.send_midi((status, note, velocity))

    def dim_element(self, element_name, color='red'):
        """
        Send a midi message to turn off the light of an element.

        element_name: the name of the element to dim
        color:        a string 'red', 'orange', or 'green'
        """
        status = MIDI_NOTE_OFF_STATUS + MIDI_CHANNEL_NUM
        note = self.element_color_to_midi[element_name][color]
        velocity = 127
        self.c_instance.send_midi((status, note, velocity))

    def dim_all_elements(self):
        """
        Reset all the elements of the controller to dimmed.

        The K2 seems to treat the different colors like different layers, the
        only reliable way to dim everything is to loop through all 3 colors.
        """
        for element, _ in self.element_color_to_midi.iteritems():
            self.dim_element(element, 'red')
        for element, _ in self.element_color_to_midi.iteritems():
            self.dim_element(element, 'orange')
        for element, _ in self.element_color_to_midi.iteritems():
            self.dim_element(element, 'green')

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
            #
            # top encoder row
            #
            'top_encoder_1': {
                'red': self.note_to_midi['e3'],
                'orange': self.note_to_midi['e6'],
                'green': self.note_to_midi['e9'],
            },
            'top_encoder_2': {
                'red': self.note_to_midi['f3'],
                'orange': self.note_to_midi['f6'],
                'green': self.note_to_midi['f9'],
            },
            'top_encoder_3': {
                'red': self.note_to_midi['f#3'],
                'orange': self.note_to_midi['f#6'],
                'green': self.note_to_midi['f#9'],
            },
            'top_encoder_4': {
                'red': self.note_to_midi['g3'],
                'orange': self.note_to_midi['g6'],
                'green': self.note_to_midi['g9'],
            },
            #
            # first pot switches row
            #
            'pot_switch_1': {
                'red': self.note_to_midi['c3'],
                'orange': self.note_to_midi['c6'],
                'green': self.note_to_midi['c9'],
            },
            'pot_switch_2': {
                'red': self.note_to_midi['c#3'],
                'orange': self.note_to_midi['c#6'],
                'green': self.note_to_midi['c#9'],
            },
            'pot_switch_3': {
                'red': self.note_to_midi['d3'],
                'orange': self.note_to_midi['d6'],
                'green': self.note_to_midi['d9'],
            },
            'pot_switch_4': {
                'red': self.note_to_midi['d#3'],
                'orange': self.note_to_midi['d#6'],
                'green': self.note_to_midi['d#9'],
            },
            #
            # second pot switches row
            #
            'pot_switch_5': {
                'red': self.note_to_midi['g#2'],
                'orange': self.note_to_midi['g#5'],
                'green': self.note_to_midi['g#8'],
            },
            'pot_switch_6': {
                'red': self.note_to_midi['a2'],
                'orange': self.note_to_midi['a5'],
                'green': self.note_to_midi['a8'],
            },
            'pot_switch_7': {
                'red': self.note_to_midi['a#2'],
                'orange': self.note_to_midi['a#5'],
                'green': self.note_to_midi['a#8'],
            },
            'pot_switch_8': {
                'red': self.note_to_midi['b2'],
                'orange': self.note_to_midi['b5'],
                'green': self.note_to_midi['b8'],
            },
            #
            # third pot switches row
            #
            'pot_switch_9': {
                'red': self.note_to_midi['e2'],
                'orange': self.note_to_midi['e5'],
                'green': self.note_to_midi['e8'],
            },
            'pot_switch_10': {
                'red': self.note_to_midi['f2'],
                'orange': self.note_to_midi['f5'],
                'green': self.note_to_midi['f8'],
            },
            'pot_switch_11': {
                'red': self.note_to_midi['f#2'],
                'orange': self.note_to_midi['f#5'],
                'green': self.note_to_midi['f#8'],
            },
            'pot_switch_12': {
                'red': self.note_to_midi['g2'],
                'orange': self.note_to_midi['g5'],
                'green': self.note_to_midi['g8'],
            },
            #
            # first matrix row
            #
            'matrix_button_a': {
                'red': self.note_to_midi['c2'],
                'orange': self.note_to_midi['c5'],
                'green': self.note_to_midi['c8'],
            },
            'matrix_button_b': {
                'red': self.note_to_midi['c#2'],
                'orange': self.note_to_midi['c#5'],
                'green': self.note_to_midi['c#8'],
            },
            'matrix_button_c': {
                'red': self.note_to_midi['d2'],
                'orange': self.note_to_midi['d5'],
                'green': self.note_to_midi['d8'],
            },
            'matrix_button_d': {
                'red': self.note_to_midi['d#2'],
                'orange': self.note_to_midi['d#5'],
                'green': self.note_to_midi['d#8'],
            },
            #
            # second matrix row
            #
            'matrix_button_e': {
                'red': self.note_to_midi['g#1'],
                'orange': self.note_to_midi['g#4'],
                'green': self.note_to_midi['g#7'],
            },
            'matrix_button_f': {
                'red': self.note_to_midi['a1'],
                'orange': self.note_to_midi['a4'],
                'green': self.note_to_midi['a7'],
            },
            'matrix_button_g': {
                'red': self.note_to_midi['a#1'],
                'orange': self.note_to_midi['a#4'],
                'green': self.note_to_midi['a#7'],
            },
            'matrix_button_h': {
                'red': self.note_to_midi['b1'],
                'orange': self.note_to_midi['b4'],
                'green': self.note_to_midi['b7'],
            },
            #
            # third matrix row
            #
            'matrix_button_i': {
                'red': self.note_to_midi['e1'],
                'orange': self.note_to_midi['e4'],
                'green': self.note_to_midi['e7'],
            },
            'matrix_button_j': {
                'red': self.note_to_midi['f1'],
                'orange': self.note_to_midi['f4'],
                'green': self.note_to_midi['f7'],
            },
            'matrix_button_k': {
                'red': self.note_to_midi['f#1'],
                'orange': self.note_to_midi['f#4'],
                'green': self.note_to_midi['f#7'],
            },
            'matrix_button_l': {
                'red': self.note_to_midi['g1'],
                'orange': self.note_to_midi['g4'],
                'green': self.note_to_midi['g7'],
            },
            #
            # fourth matrix row
            #
            'matrix_button_m': {
                'red': self.note_to_midi['c1'],
                'orange': self.note_to_midi['c4'],
                'green': self.note_to_midi['c7'],
            },
            'matrix_button_n': {
                'red': self.note_to_midi['c#1'],
                'orange': self.note_to_midi['c#4'],
                'green': self.note_to_midi['c#7'],
            },
            'matrix_button_o': {
                'red': self.note_to_midi['d1'],
                'orange': self.note_to_midi['d4'],
                'green': self.note_to_midi['d7'],
            },
            'matrix_button_p': {
                'red': self.note_to_midi['d#1'],
                'orange': self.note_to_midi['d#4'],
                'green': self.note_to_midi['d#7'],
            },
            #
            # bottom row encoder buttons
            #
            'layer_button': {
                'red': self.note_to_midi['c0'],
                'orange': self.note_to_midi['e0'],
                'green': self.note_to_midi['g#0'],
            },
            'exit_setup_button': {
                'red': self.note_to_midi['d#0'],
                'orange': self.note_to_midi['g0'],
                'green': self.note_to_midi['b0'],
            }
        }

