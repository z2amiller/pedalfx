# Smooth Brain Overdrive

The smooth brain overdrive is based on the [PedalPCB 'Tommy III'](https://www.pedalpcb.com/product/tommy/)
which in turn is based on the Paul Cochrane Timmy V3.

This pedal has a good clean boost, as well as a high-gain switch to throw it into overdrive/distortion
territory.  This pedal is notable for the way the bass cutoff works, cutting the bass in the first
amiplifier stage to give more clarity to the mids and highs in the later stage.

## Controls

* Volume
* Gain
* Bass
* Treble
* NARF! (Enabling this greatly boosts the gain of the circuit at the cost of more noise)

## Internal Controls:

* Internal switch to change diode clipping from symmetric to asymmetric.

## Current Revision: 0.4

## Revision History:

### 0.4:  Added socket for op-amp and through-hole capacitor to help tune feedback issues.

This revision fixes the shorted via, and also replaces the SMD op-amp with a socketed DIP version
to allow some more experimentation with different op-amps.

### 0.3:  Fixed some grounding and op-amp feedback issues.

This one has an internal short from VREF to GND. :-(

It is fixable by drilling out the shorted via, and also requires some modifications to the capacitor
(adding more capacitance to the feedback loop), as well as very careful routing of the internal wiring.
If the internal wiring (specitically, the input/output wires) get too close to the board, it can start to
oscillate and whine when the 'high gain' switch is engaged.

This also switches from a 2-layer to a 4-layer design in an attempt to control the noise and feedback.

### 0.2:  Switched some components inadvertantly connected to GND instead of VREF

### 0.1:  Initial Version

## Links

* [Internal Repository](https://github.com/z2amiller/fx-Tommy)
