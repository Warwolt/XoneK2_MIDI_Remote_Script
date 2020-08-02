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

MIDI_CHANNEL_NUM = 15 - 1 # The Xone K2 uses midi channel 15
NUM_TRACKS = 4
NORMALIZED_ZERO_DB = 0.85000002384185791015625 # the value Live uses for 0 dB
MUTE_BUTTON_COLOR = 'red'
CUE_BUTTON_COLOR = 'orange'
EQ_KILL_COLOR = 'red'
EQ_CUT_COLOR = 'green'


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

        with self.component_guard():
            self._set_suppress_rebuild_requests(True)
            self.c_instance = c_instance
            self.song = c_instance.song()
            self.tracks = self.song.visible_tracks
            self.note_to_midi = self._create_note_to_midi_dict()
            self.element_color_to_midi = self._create_element_color_dict()

            self.setup_data_structures()
            self.initialize_controller_components()

    def disconnect(self):
        self.dim_all_elements()

    def setup_data_structures(self):
        self.coarse_encoder_is_pushed = False
        self.fine_encoder_pushed = False
        self.scrobble_encoder_pushed = [False] * NUM_TRACKS
        self.eq3_devices = [None] * NUM_TRACKS
        self.eq3_device_on_params = [None] * NUM_TRACKS
        self.eq3_hi_cut_params = [None] * NUM_TRACKS
        self.eq3_mid_cut_params = [None] * NUM_TRACKS
        self.eq3_low_cut_params = [None] * NUM_TRACKS
        self.eq3_hi_gain_params = [None] * NUM_TRACKS
        self.eq3_mid_gain_params = [None] * NUM_TRACKS
        self.eq3_low_gain_params = [None] * NUM_TRACKS

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

        # Track stop data
        self.track_stop_buttons = [
            Button(0x18), Button(0x19),
            Button(0x1A), Button(0x1B)]
        self.track_stop_elements = [
            'matrix_button_m', 'matrix_button_n',
            'matrix_button_o', 'matrix_button_p']

        # Volume fader data
        self.volume_faders = [
            Fader(0x10), Fader(0x11),
            Fader(0x12), Fader(0x13)]

        # High EQ data
        self.hi_eq_knobs = [
            Knob(0x04), Knob(0x05),
            Knob(0x06), Knob(0x07)]
        self.hi_eq_cut_buttons = [
            Button(0x30), Button(0x31),
            Button(0x32), Button(0x33)]
        self.hi_eq_cut_elements = [
            'pot_switch_1', 'pot_switch_2',
            'pot_switch_3', 'pot_switch_4']

        # Mid EQ data
        self.mid_eq_knobs = [
            Knob(0x08), Knob(0x09),
            Knob(0x0A), Knob(0x0B)]
        self.mid_eq_cut_buttons = [
            Button(0x2C), Button(0x2D),
            Button(0x2E), Button(0x2F)]
        self.mid_eq_cut_elements = [
            'pot_switch_5', 'pot_switch_6',
            'pot_switch_7', 'pot_switch_8']

        # Low EQ data
        self.low_eq_knobs = [
            Knob(0x0C), Knob(0x0D),
            Knob(0x0E), Knob(0x0F)]
        self.low_eq_cut_buttons = [
            Button(0x28), Button(0x29),
            Button(0x2A), Button(0x2B)]
        self.low_eq_cut_elements = [
            'pot_switch_9', 'pot_switch_10',
            'pot_switch_11', 'pot_switch_12']

        # Scrobble data
        self.scrobble_knobs = [
            Knob(0x00), Knob(0x01),
            Knob(0x02), Knob(0x03)]
        self.scrobble_push = [
            Button(0x34), Button(0x35),
            Button(0x36), Button(0x37)]

    def initialize_controller_components(self):
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
            kill_push_listener = partial(self.on_eq_kill_button_push, i)
            self.eq_kill_buttons[i].add_value_listener(kill_push_listener)

        # Initialize track stop buttons:
        for i in range(NUM_TRACKS):
            stop_listener = partial(self.on_track_stop_button_push, i)
            self.track_stop_buttons[i].add_value_listener(stop_listener)

        # Initialize volume faders:
        for i in range(NUM_TRACKS):
            fader_move_listener = partial(self.on_volume_fader_move, i)
            self.volume_faders[i].add_value_listener(fader_move_listener)

        # Initialize high EQ buttons:
        for i in range(NUM_TRACKS):
            hi_cut_listener = partial(self.on_eq_cut_button_push,
                self.eq3_hi_cut_params, self.draw_hi_eq_cut, i)
            self.hi_eq_cut_buttons[i].add_value_listener(hi_cut_listener)
            self.draw_mid_eq_cut(i)

        # Initialize mid EQ buttons:
        for i in range(NUM_TRACKS):
            mid_cut_listener = partial(self.on_eq_cut_button_push,
                self.eq3_mid_cut_params, self.draw_mid_eq_cut, i)
            self.mid_eq_cut_buttons[i].add_value_listener(mid_cut_listener)
            self.draw_mid_eq_cut(i)

        # Initialize low EQ buttons:
        for i in range(NUM_TRACKS):
            low_cut_listener = partial(self.on_eq_cut_button_push,
                self.eq3_low_cut_params, self.draw_low_eq_cut, i)
            self.low_eq_cut_buttons[i].add_value_listener(low_cut_listener)
            self.draw_low_eq_cut(i)

        # Initialize high EQ knobs:
        for i in range(NUM_TRACKS):
            hi_gain_listener = partial(
                self.on_eq_knob_turn, self.eq3_hi_gain_params, i)
            self.hi_eq_knobs[i].add_value_listener(hi_gain_listener)

        # Initialize mid EQ knobs:
        for i in range(NUM_TRACKS):
            mid_gain_listener = partial(
                self.on_eq_knob_turn, self.eq3_mid_gain_params, i)
            self.mid_eq_knobs[i].add_value_listener(mid_gain_listener)

        # Initialize low EQ knobs:
        for i in range(NUM_TRACKS):
            low_gain_listener = partial(
                self.on_eq_knob_turn, self.eq3_low_gain_params, i)
            self.low_eq_knobs[i].add_value_listener(low_gain_listener)

        # Initialize scrobble knobs:
        for i in range(NUM_TRACKS):
            scrobble_encoder_listener = partial(self.on_scrobble_change, i)
            scrobble_push_listener = partial(self.on_scrobble_encoder_push, i)
            self.scrobble_knobs[i].add_value_listener(scrobble_encoder_listener)
            self.scrobble_push[i].add_value_listener(scrobble_push_listener)

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
            if self.fine_encoder_pushed:
                self.song.tempo += 0.01
            else:
                self.song.tempo += 0.1
        else:
            if self.fine_encoder_pushed:
                self.song.tempo -= 0.01
            else:
                self.song.tempo -= 0.1

    def on_fine_encoder_push(self, value):
        """
        Called when the fine tempo encoder is pushed.

        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        if value == 127:
            self.fine_encoder_pushed = True
        else:
            self.fine_encoder_pushed = False

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

    def on_track_stop_button_push(self, index, value):
        """
        Stops all clips on the associated track when pushed.

        index: index of track to associate with this listener
        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        track = self.tracks[index]
        stop_element = self.track_stop_elements[index]
        if value == 127:
            self.light_up_element(stop_element, 'red')
            track.stop_all_clips(Quantized=False)
        else:
            self.dim_element(stop_element, 'red')

    def on_volume_fader_move(self, index, value):
        """
        Sets the associated track volume according to the fader position.

        The fader maps the range [0, 127] to the range [-inf dBm, 0 dB], by
        scaling the normalized fader MIDI value by the zero db value.
        Note: Live uses the value 1.0 as 6 dB and 0.85 for 0 dB.

        index: index of track to associate with this listener
        value: MIDI control change value, 0-127
        """
        track = self.tracks[index]
        normalized_fader_value = (value + 1.0) / 128.0
        new_volume = normalized_fader_value * NORMALIZED_ZERO_DB
        track.mixer_device.volume.value = new_volume

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
            device_on_param = get_eq3_parameter(eq3, 'Device On')
            self.eq3_device_on_params[index] = device_on_param
            if device_on_param is not None:
                device_on_listener = partial(self.draw_eq_kill, index)
                device_on_param.add_value_listener(device_on_listener)
            # find 'hi on' parameter
            hi_cut_param = get_eq3_parameter(eq3, 'HighOn')
            self.eq3_hi_cut_params[index] = hi_cut_param
            if hi_cut_param is not None:
                hi_cut_listener = partial(self.draw_hi_eq_cut, index)
                hi_cut_param.add_value_listener(hi_cut_listener)
            # find 'mid on' parameter
            mid_cut_param = get_eq3_parameter(eq3, 'MidOn')
            self.eq3_mid_cut_params[index] = mid_cut_param
            if mid_cut_param is not None:
                mid_cut_listener = partial(self.draw_mid_eq_cut, index)
                mid_cut_param.add_value_listener(mid_cut_listener)
            # find 'low on' parameter
            low_cut_param = get_eq3_parameter(eq3, 'LowOn')
            self.eq3_low_cut_params[index] = low_cut_param
            if low_cut_param is not None:
                low_cut_listener = partial(self.draw_low_eq_cut, index)
                low_cut_param.add_value_listener(low_cut_listener)
            # find 'hi gain' parameter
            hi_gain_param = get_eq3_parameter(eq3, 'GainHi')
            self.eq3_hi_gain_params[index] = hi_gain_param
            # find 'mid gain' parameter
            mid_gain_param = get_eq3_parameter(eq3, 'GainMid')
            self.eq3_mid_gain_params[index] = mid_gain_param
            # find 'low gain' parameter
            low_gain_param = get_eq3_parameter(eq3, 'GainLo')
            self.eq3_low_gain_params[index] = low_gain_param
        else:
            self.eq3_device_on_params[index] = None
            self.eq3_hi_cut_params[index] = None
            self.eq3_mid_cut_params[index] = None
            self.eq3_low_cut_params[index] = None
        # Update views
        self.draw_eq_kill(index)
        self.draw_hi_eq_cut(index)
        self.draw_mid_eq_cut(index)
        self.draw_low_eq_cut(index)

    def on_eq_kill_button_push(self, index, value):
        """
        Toggle the EQ3 on-state to create a EQ kill functionality.

        index: index of track to associate with this listener
        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        eq3_device_on = self.eq3_device_on_params[index]
        if eq3_device_on is not None and value == 127:
            eq3_device_on.value = abs(eq3_device_on.value - 1.0)
        self.draw_eq_kill(index)

    def on_eq_cut_button_push(self, eq3_cut_params, draw_button, index, value):
        """
        Kill an EQ3 band of the associated track.

        eq3_cut_params: list of 'EQ Three' DeviceParameter instances
        draw_button: function for drawing the button
        index: index of track to associate with this listener
        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        eq3_cut_param = eq3_cut_params[index]
        if eq3_cut_param is not None and value == 127:
            eq3_cut_param.value = abs(eq3_cut_param.value - 1.0)
        draw_button(index)

    def on_eq_knob_turn(self, gain_params, index, value):
        """
        Change the gain of the EQ band of the associated track.

        The knob is mapped to give 0 dB at 12 o'clock, 6 dB at full twist right
        and -inf dB at full twist left.

        gain_params: list containing 'EQ Three' Device.Device instances
        index: index of track to associate with this listener
        value: MIDI control change value, 0-127
        """
        gain_param = gain_params[index]
        if gain_param is not None:
            normalized_knob_value = (value + 1.0) / 128.0
            dead_zone_x_range = 0.1
            lower_x_range = 0.5 - dead_zone_x_range / 2
            lower_y_max = NORMALIZED_ZERO_DB
            upper_x_range = 0.5 + dead_zone_x_range / 2
            upper_y_range = 1.0 - lower_y_max
            upper_y_max = 1.0
            # Left twist, -inf dB to 0 dB
            if normalized_knob_value <= lower_x_range:
                scaled_knob_value = normalized_knob_value / lower_x_range
                new_gain_value = scaled_knob_value * lower_y_max
            # Dead zone 0 dB
            elif normalized_knob_value <= (lower_x_range + dead_zone_x_range):
                new_gain_value = NORMALIZED_ZERO_DB
            # Right twist, 0 dB to 6 dB
            else:
                shifted_knob_value = normalized_knob_value - lower_x_range
                scaled_knob_value = shifted_knob_value / upper_x_range
                upper_y_value = scaled_knob_value * upper_y_range
                new_gain_value = lower_y_max + upper_y_value
            gain_param.value = new_gain_value

    def on_scrobble_encoder_push(self, index, value):
        """
        Called when scrobble knob is pushed/released and stores it's state

        index: index of track to associate with this listener.
        value: MIDI note value (127 = pushed, 0 = depressed)
        """
        self.scrobble_encoder_pushed[index] = True if value == 127 else False

    def on_scrobble_change(self, index, value):
        """
        Called when scrobble knob is turned, moves beat forward/backward.

        Moves the playback one bar forward/backward, or a quarter beat if
        the knob is pressed.

        index: index of track to associate with this listener.
        value: MIDI note value (1 = right turn, 127 = left turn)
        """
        track = self.tracks[index]
        playback_index = track.playing_slot_index
        encoder_pushed = self.scrobble_encoder_pushed[index]
        # Move playback position if clip is playing
        if playback_index > -1:
            num_beats = 1 if encoder_pushed else 4
            playback_offset = -num_beats if value == 127 else num_beats
            clip = track.clip_slots[playback_index].clip
            clip.position += playback_offset

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
        if device_on_param is not None and device_on_param.value == 1.0:
            self.light_up_element(eq_kill_element, EQ_KILL_COLOR)
        else:
            self.dim_element(eq_kill_element, EQ_KILL_COLOR)

    def draw_hi_eq_cut(self, index):
        """
        Light up or dim the high EQ button based on its state.

        index: index of track associated with the high cut button
        """
        hi_cut_element = self.hi_eq_cut_elements[index]
        hi_cut = self.eq3_hi_cut_params[index]
        if hi_cut is not None and hi_cut.value == 1.0:
            self.light_up_element(hi_cut_element, EQ_CUT_COLOR)
        else:
            self.dim_element(hi_cut_element, EQ_CUT_COLOR)

    def draw_mid_eq_cut(self, index):
        """
        Light up or dim the mid EQ button based on its state.

        index: index of track associated with the mid cut button
        """
        mid_cut_element = self.mid_eq_cut_elements[index]
        mid_cut = self.eq3_mid_cut_params[index]
        if mid_cut is not None and mid_cut.value == 1.0:
            self.light_up_element(mid_cut_element, EQ_CUT_COLOR)
        else:
            self.dim_element(mid_cut_element, EQ_CUT_COLOR)

    def draw_low_eq_cut(self, index):
        """
        Light up or dim the low EQ button based on its state.

        index: index of track associated with the low cut button
        """
        low_cut_element = self.low_eq_cut_elements[index]
        low_cut = self.eq3_low_cut_params[index]
        if low_cut is not None and low_cut.value == 1.0:
            self.light_up_element(low_cut_element, EQ_CUT_COLOR)
        else:
            self.dim_element(low_cut_element, EQ_CUT_COLOR)

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
    Tries to find the first 'EQ Three' device on a track.

    track: Track.Track instance to inspect
    """
    eq3 = filter(lambda device: device.name == 'EQ Three', track.devices)
    return eq3[0] if len(eq3) > 0 else None

def get_eq3_parameter(eq3, param_name):
    """
    Tries to find a parameter in a 'EQ Three' device.

    eq3: 'EQ Three' Device.Device instance to inspect.
    param_name: Name of the parameter to find
    """
    parameter = filter(lambda param: param.name == param_name, eq3.parameters)
    return parameter[0] if len(parameter) > 0 else None
