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
NUM_TRACKS = 4
MUTE_BUTTON_COLOR = 'red'
CUE_BUTTON_COLOR = 'orange'
EQ_KILL_COLOR = 'red'


def Button(note_num, name=None):
    button = ButtonElement(True, MIDI_NOTE_TYPE, MIDI_CHANNEL_NUM, note_num)
    if name is not None:
        button.name = name
    return button


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
            self.tracks = self.song.visible_tracks
            self.note_to_midi = self._create_note_to_midi_dict()
            self.element_color_to_midi = self._create_element_color_dict()
            self.coarse_encoder_is_pushed = False
            self.fine_encoder_pushed = False
            self.dim_all_elements()
            self.eq3_devices = [None] * NUM_TRACKS
            self.eq3_device_on_params = [None] * NUM_TRACKS

            # Mute data
            self.mute_buttons = [
                Button(0x1C), Button(0x1D),
                Button(0x1E), Button(0x1F)]
            self.mute_elements = [
                'matrix_button_i', 'matrix_button_j',
                'matrix_button_k', 'matrix_button_l']
            # Cue data
            self.cue_buttons = [
                Button(0x24), Button(0x25),
                Button(0x26), Button(0x27)]
            self.cue_elements = [
                'matrix_button_a', 'matrix_button_b',
                'matrix_button_c', 'matrix_button_d']
            # EQ kill data
            self.eq_kill_buttons = [
                Button(0x20), Button(0x21),
                Button(0x22), Button(0x23)]
            self.eq_kill_elements = [
                'matrix_button_e', 'matrix_button_f',
                'matrix_button_g', 'matrix_button_h']

            # Find EQ devices and update bindings
            for i in range(NUM_TRACKS):
                track = self.tracks[i]
                dev_change_listener = partial(self.update_devices_bindings, i)
                track.add_devices_listener(dev_change_listener)
                self.update_devices_bindings(i) # look for any existing devies

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

            # Initialize mute buttons
            for i in range(NUM_TRACKS):
                on_mute_change_listener = partial(self.draw_mute_button, i)
                self.tracks[i].add_mute_listener(on_mute_change_listener)
                on_mute_button_listener = partial(self.on_mute_button_push, i)
                self.mute_buttons[i].add_value_listener(on_mute_button_listener)
                self.draw_mute_button(i)

            # Initialize cue buttons
            for i in range(NUM_TRACKS):
                on_cue_change_listener = partial(self.draw_cue_button, i)
                self.tracks[i].add_solo_listener(on_cue_change_listener)
                on_cue_button_listener = partial(self.on_cue_button_push, i)
                self.cue_buttons[i].add_value_listener(on_cue_button_listener)
                self.draw_cue_button(i)

            # Initialize EQ kill buttons:
            for i in range(NUM_TRACKS):
                push_listener = partial(self.on_eq_kill_button_push, i)
                self.eq_kill_buttons[i].add_value_listener(push_listener)

            # Initialize track stop buttons:
            for i in range(NUM_TRACKS):
                pass

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
        """
        Called when the coarse tempo encoder is rotated.
        Change the tempo in whole steps, or in tenths if encoder is pushed.

        value: MIDI note value (1 = right turn, 127 = left turn)
        """
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
        """
        Called when the coarse tempo encoder is pushed.

        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        if value == 127:
            self.coarse_encoder_is_pushed = True
        else:
            self.coarse_encoder_is_pushed = False

    def on_fine_tempo_change(self, value):
        """
        Called when the fine tempo encoder is rotated.
        Change the tempo in tenths, or in cents if encoder is pushed.

        value: MIDI note value (1 = right turn, 127 = left turn)
        """
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
        """
        Called when the fine tempo encoder is pushed.

        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        if value == 127:
            self._fine_encoder_is_pushed = True
        else:
            self._fine_encoder_is_pushed = False

    def on_mute_button_push(self, index, value):
        """
        Toggles the muted state of the associated track.

        index: index of track to associate with this listener.
        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        track = self.tracks[index]
        mute_element = self.mute_elements[index]
        if value == 127:
            track.mute = not track.mute
        if not track.mute:
            self.light_up_element(mute_element, MUTE_BUTTON_COLOR)
        else:
            self.dim_element(mute_element, MUTE_BUTTON_COLOR)

    def on_cue_button_push(self, index, value):
        """
        Toggles the cue state of the associated track.

        index: index of track to associate with this listener
        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        track = self.tracks[index]
        if value == 127:
            track.solo = not track.solo
        self.draw_cue_button(index)

    def update_devices_bindings(self, index):
        """
        Called whenever a device is added or removed from associated track.

        This listener is used to make sure that this script is kept in sync
        with the available EQ3 devices in the Live session.

        index: index of track to associate with this listener
        """
        # Find devices and parameters
        track = self.tracks[index]
        eq3 = find_eq3_device(track)
        self.eq3_devices[index] = eq3
        if eq3 is not None:
            # find 'device on' parameter
            device_on_param = get_eq3_device_on_parameter(eq3)
            self.eq3_device_on_params[index] = device_on_param
            # add parameter change listener
            if device_on_param is not None:
                device_on_listener = partial(self.draw_eq_kill, index)
                device_on_param.add_value_listener(device_on_listener)
        else:
            self.eq3_device_on_params[index] = None
        # Update views
        self.draw_eq_kill(index)


    def on_eq_kill_button_push(self, index, value):
        """
        Toggle the 'EQ Three' on-state to create a EQ kill functionality.

        index: index of track to associate with this listener
        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        eq3_device_on = self.eq3_device_on_params[index]
        if eq3_device_on is not None:
            if value == 127:
                eq3_device_on.value = abs(eq3_device_on.value - 1.0)
            self.draw_eq_kill(index)

    def draw_mute_button(self, index):
        """
        Light up or dim the mute button based on its state.

        index: index of track associated with the mute button
        """
        track = self.tracks[index]
        mute_element = self.mute_elements[index]
        if not track.mute:
            self.light_up_element(mute_element, MUTE_BUTTON_COLOR)
        else:
            self.dim_element(mute_element, MUTE_BUTTON_COLOR)

    def draw_cue_button(self, index):
        """
        Light up or dim the cue button based on its state.

        index: index of track associated with the cue button
        """
        track = self.tracks[index]
        cue_element = self.cue_elements[index]
        if track.solo:
            self.light_up_element(cue_element, CUE_BUTTON_COLOR)
        else:
            self.dim_element(cue_element, CUE_BUTTON_COLOR)

    def draw_eq_kill(self, index):
        """
        Light up or dim the EQ kill button based on its state.

        index: index of track associated with the eq kill button
        """
        eq_kill_element = self.eq_kill_elements[index]
        device_on_param = self.eq3_device_on_params[index]
        if device_on_param is None:
            self.dim_element(eq_kill_element, EQ_KILL_COLOR)
        elif device_on_param.value == 1.0:
            self.light_up_element(eq_kill_element, EQ_KILL_COLOR)
        else:
            self.dim_element(eq_kill_element, EQ_KILL_COLOR)

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


def find_eq3_device(track):
    """
    Tries to find the first 'EQ Three' device on the track and returns it if
    it's found.

    track: Track.Track instance to inspect
    """
    eq3 = filter(lambda device: device.name == 'EQ Three', track.devices)
    return eq3[0] if len(eq3) > 0 else None

def get_eq3_device_on_parameter(eq3):
    """ """
    device_on = filter(lambda param: param.name == 'Device On', eq3.parameters)
    return device_on[0] if len(device_on) > 0 else None
