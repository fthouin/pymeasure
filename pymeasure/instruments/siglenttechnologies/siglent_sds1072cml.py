#
# This file is part of the PyMeasure package.
#
# Copyright (c) 2013-2024 PyMeasure Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import struct

from pymeasure.instruments import Channel, Instrument
from pymeasure.instruments.generic_types import SCPIMixin
from pymeasure.instruments.validators import truncated_discrete_set, truncated_range


class VoltageChannel(Channel):
    """
    ===========================================================
    Implementation of a SIGLENT SDS1072CML Oscilloscope channel
    ===========================================================
    """

    vertical_division = Channel.control(
        "C{ch}:VDIV?",
        "C{ch}:VDIV %s",
        "Control the vertical sensitivity of a channel.",
        validator=truncated_range,
        values=[2e-3, 10],
        get_process=lambda v: float(v.split(" ", 1)[-1][:-1]),
        set_process=lambda v: "%.2eV" % v,
    )

    coupling = Channel.control(
        "C{ch}:CPL?",
        "C{ch}:CPL %s1M",
        "Control the channel coupling mode. (see UM p. 35)",
        validator=truncated_discrete_set,
        values={"DC": "D", "AC": "A"},
        map_values=True,
        get_process=lambda v: v.split(" ", 1)[-1][0],
    )

    def get_waveform(self):
        """Return the waveforms displayed in the channel.

        Return:
        -------
        - time: (1d array) the time in seconds since the trigger epoch for every voltage value in
            the waveforms
        - voltages: (1d array) the waveform in V

        """
        command = "C{ch}:WF? DAT2"
        descriptorDictionnary = self.get_desc()
        self.write(command)
        response = self.read_bytes(count=-1, break_on_termchar=True)
        rawWaveform = list(
            struct.unpack_from(
                "%db" % descriptorDictionnary["numDataPoints"],
                response,
                offset=descriptorDictionnary["descriptorOffset"],
            ),
        )
        waveform = [
            point * descriptorDictionnary["verticalGain"] - descriptorDictionnary["verticalOffset"]
            for point in rawWaveform
        ]
        timetags = [
            i * descriptorDictionnary["horizInterval"] + descriptorDictionnary["horizOffset"]
            for i in range(len(rawWaveform))
        ]
        return timetags, waveform

    def get_desc(self):
        """Get the descriptor of data being sent when querying device for waveform
        :return:
        dict: A dictionnary with the keys:
        - numDataPoints: the number of poitns in the waveform
        - verticalGain: the voltage increment per code value (in V)
        - verticalOffset: the voltage offset to add to the decoded voltage values
        - horizInterval: the time interval between points in s
        - horizOffset:the offset to add to the time steps
        - descriptorOffset: Length of the C1:WF ALL,#9000000346 message

        """
        command = "C{ch}:WF? DESC"
        self.write(command)
        descriptor = self.read_bytes(count=-1, break_on_termchar=True)
        descriptorOffset = 21
        (numDataPoints,) = struct.unpack_from(
            "l",
            descriptor,
            offset=descriptorOffset + 60,
        )
        (verticalGain,) = struct.unpack_from(
            "f",
            descriptor,
            offset=descriptorOffset + 156,
        )
        (verticalOffset,) = struct.unpack_from(
            "f",
            descriptor,
            offset=descriptorOffset + 160,
        )
        (horizInterval,) = struct.unpack_from(
            "f",
            descriptor,
            offset=descriptorOffset + 176,
        )
        (horizOffset,) = struct.unpack_from(
            "d",
            descriptor,
            offset=descriptorOffset + 180,
        )
        descriptorDictionnary = {
            "numDataPoints": numDataPoints,
            "verticalGain": verticalGain,
            "verticalOffset": verticalOffset,
            "horizInterval": horizInterval,
            "horizOffset": horizOffset,
            "descriptorOffset": descriptorOffset,
        }
        return descriptorDictionnary


class TriggerChannel(Channel):
    """
    =========================================
    Implementation of trigger control channel
    =========================================
    """

    triggerConfDict = {}

    def get_triggerConfig(self):
        """Get the current trigger configuration as a dict with keys:
        - "type": condition that will trigger the acquisition of waveforms [EDGE,
            slew,GLIT,intv,runt,drop]
        - "source": trigger source (str, {EX,EX/5,C1,C2})
        - "hold_type": hold type (refer to page 131 of programing guide)
        - "hold_value1": hold value1 (refer to page 131 of programing guide)
        - "level": Level at which the trigger will be set (float)
        - "slope": (str,{POS,NEG,WINDOW}) Triggers on rising, falling or Window.
        - "mode": behavior of the trigger following a triggering event
            (str, {NORM, AUTO, SINGLE,STOP})
        - "coupling":  (str,{AC,DC}) Coupling to the trigger channel

        and updates the internal configuration status
        """
        self.triggerConfDict.update(self.trigger_setup)
        self.triggerConfDict.update(self.trigger_level)
        self.triggerConfDict.update(self.trigger_slope)
        self.triggerConfDict.update(self.trigger_mode)
        self.triggerConfDict.update(self.trigger_coupling)
        return self.triggerConfDict

    trigger_setup = Channel.measurement(
        "TRSE?",
        docs="""Get the current trigger setup as a dict with keys:
        - "type": condition that will trigger the acquisition of waveforms [EDGE,
            slew,GLIT,intv,runt,drop]
        - "source": trigger source (str, {EX,EX/5,C1,C2})
        - "hold_type": hold type (refer to page 131 of programing guide)
        - "hold_value1": hold value1 (refer to page 131 of programing guide)

        """,
        preprocess_reply=lambda v: v.split(" ", 1)[1],
        get_process=lambda v: {
            "type": v[0],
            "source": v[2],
            "hold_type": v[4],
            "hold_value1": v[6],
        },
    )

    trigger_level = Channel.measurement(
        "TRLV?",
        docs="""Get the current trigger level as a dict with keys:
        - "source": trigger source whose level will be changed (str, {EX,EX/5,C1,C2})
        - "level": Level at which the trigger will be set (float)

        """,
        get_process=lambda v: {
            "source": v.split(":", 1)[0],
            "level": float(v.split(" ", 1)[-1][:-2]),
        },
    )

    trigger_slope = Channel.measurement(
        "TRSL?",
        docs="""Get the current trigger slope as a dict with keys:
        - "source": trigger source whose level will be changed (str, {EX,EX/5,C1,C2})
        - "slope": (str,{POS,NEG,WINDOW}) Triggers on rising, falling or Window.

        """,
        get_process=lambda v: {
            "source": v.split(":", 1)[0],
            "slope": v.split(" ", 1)[-1],
        },
    )

    trigger_mode = Channel.measurement(
        "TRMD?",
        docs="""Get the current trigger mode as a dict with keys:
        - "mode": behavior of the trigger following a triggering event
        (str, {NORM, AUTO, SINGLE,STOP})

        """,
        get_process=lambda v: {"mode": v.split(" ", 1)[-1]},
    )

    trigger_coupling = Channel.measurement(
        "TRCP?",
        docs="""Get the current trigger coupling as a dict with keys:
        - "source": trigger source whose coupling will be changed (str, {EX,EX/5,C1,C2})
        - "coupling":  (str,{AC,DC}) Coupling to the trigger channel

        """,
        get_process=lambda v: {
            "source": v.split(":", 1)[0],
            "coupling": v.split(" ", 1)[-1],
        },
    )

    def set_triggerConfig(self, **kwargs):
        """Set the current trigger configuration with keys:
        - "type": condition that will trigger the acquisition of waveforms [EDGE,
            slew,GLIT,intv,runt,drop]
        - "source": trigger source (str, {EX,EX/5,C1,C2})
        - "hold_type": hold type (refer to page 131 of programing guide)
        - "hold_value1": hold value1 (refer to page 131 of programing guide)
        - "level": Level at which the trigger will be set (float)
        - "slope": (str,{POS,NEG,WINDOW}) Triggers on rising, falling or Window.
        - "mode": behavior of the trigger following a triggering event
            (str, {NORM, AUTO, SINGLE,STOP})
        - "coupling":  (str,{AC,DC}) Coupling to the trigger channel

        Returns a flag indicating if all specified entries were correctly set on the oscilloscope
        and updates the interal trigger configuration
        """
        triggerConfDict = self.get_triggerConfig()
        # self.triggerConfDict=triggerConfDict
        setProcesses = {
            "setup": lambda dictIn: (
                dictIn.get("type"),
                dictIn.get("hold_type"),
                dictIn.get("hold_value1"),
            ),
            "level": lambda dictIn: "%.2eV" % dictIn.get("level"),
            "coupling": lambda dictIn: dictIn.get("coupling"),
            "slope": lambda dictIn: dictIn.get("slope"),
            "mode": lambda dictIn: dictIn.get("mode"),
        }
        setCommands = {
            "setup": "TRSE %s,SR,{ch},HT,%s,HV,%s",
            "level": "{ch}:TRLV %s",
            "coupling": "{ch}:TRCP %s",
            "slope": "{ch}:TRSL %s",
            "mode": "TRMD %s",
        }
        setValues = {  # For a given change in conf dict,find the relevant command to be called
            "setup": ["source", "type", "hold_type", "hold_value1"],
            "level": ["level"],
            "coupling": ["coupling"],
            "slope": ["slope"],
            "mode": ["mode"],
        }
        if kwargs.get("source") is not None:
            self.id = kwargs["source"]
        changedValues = [key for key in kwargs if triggerConfDict[key] != kwargs[key]]
        processToChange = [
            key for key in setValues if any([value in changedValues for value in setValues[key]])
        ]
        for changedKey in changedValues:
            triggerConfDict[changedKey] = kwargs[changedKey]
        for processKey in processToChange:
            self.write(
                setCommands[processKey] % setProcesses[processKey](triggerConfDict),
            )
        self.triggerConfDict = self.get_triggerConfig()
        statusFlag = self.triggerConfDict == triggerConfDict
        return statusFlag


class SDS1072CML(SCPIMixin, Instrument):
    """
    ==============================================
    Represents the SIGLENT SDS1072CML Oscilloscope
    ==============================================
    """

    def __init__(self, adapter, name="Siglent SDS1072CML Oscilloscope", **kwargs):
        super().__init__(adapter, name, **kwargs)

    channel_1 = Instrument.ChannelCreator(VoltageChannel, "1")
    channel_2 = Instrument.ChannelCreator(VoltageChannel, "2")
    trigger = Instrument.ChannelCreator(TriggerChannel, "")

    timeDiv = Instrument.control(
        ":TDIV?",
        ":TDIV %s",
        "Set the time division to the closest possible value,rounding downwards.",
        validator=truncated_range,
        values=[5e-9, 50],
        set_process=lambda v: "%.2eS" % v,
        get_process=lambda v: float(v.split(" ", 1)[-1][:-1]),
    )

    status = Instrument.control(
        "SAST?",
        None,
        "Get the sampling status of the scope (Stop, Ready, Trig'd, Armed)",
        get_process=lambda v: v.split(" ", 1)[-1],
    )

    internal_state = Instrument.control(
        "INR?",
        None,
        "Get the scope's Internal state change register and clears it.",
        get_process=lambda v: v.split(" ", 1)[-1],
    )

    is_ready = Instrument.control(
        "SAST?",
        None,
        "Get a boolean flat indicating if the scope is ready for the next acquisition",
        get_process=lambda v: True
        if (v.split(" ", 1)[-1] in ["Stop", "Ready", "Armed"])
        else False,
    )

    def wait(self, time):
        """Stop the scope from doing anything until it has completed the current acquisition (p.146)
        param time: time in seconds to wait for
        """
        self.write("WAIT %d" % int(time))

    def arm(self):
        """Change the acquisition mode from 'STOPPED' to 'SINGLE'. Useful to ready scope for the
        next acquisition"""
        if self.is_ready:
            self.write("ARM")
            return True
        else:
            return False

    template = Instrument.control(
        "TMP?",
        None,
        """Get a copy of the template that describes the various logical entities making up a
        complete waveform.
        In particular, the template describes in full detail the variables contained in the
        descriptor part of a waveform.
        """,
    )