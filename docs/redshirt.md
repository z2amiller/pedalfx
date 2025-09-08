# Redshirt Phaser

This is based on the PedalPCB XC Phase, which is in turn based on the MXR 90 Phaser.

These can be complicated to build, as they require 4 closely matched JFET transitiors
in order to phase properly.

## Controls

* Rate (Sets the rate of the phase effect)
* Depth (Sets the depth of the phase effect)
* Color (Changes the offset of the phase to affect the sound)
* Resonance: Affects how much feedback reaches back to the first phase.  Changes between the
             'block' and 'script' models of the original versions of the MXR 90, with a setting
              halfway between.

## Internal Controls

* Bias:  This is a tricky pedal to bias with only a small range that the phaser effect works.
         It has been set 'at the factory' for the best sound, but might need to be adjusted on
         a different power supply.

## Current Revision: 0.3

## Revision History

### 0.3:  Chuck's Boneyard Edition

This edition adds the 'color' and 'depth' knobs, and removes the 'vibe' and '90/45' switches.
It contains the Chuck D. Bones / Celestial Engineering mods to this circuit described in 
[this](https://forum.pedalpcb.com/threads/this-week-on-the-breadboard-phase-90.19506) thread.

### 0.2:  Original z2a PCB edition

First working edition.  Has only the 'Rate' knob as a control, with 'script/block', '90/45',
and a 'vibe' switch to add more feedback.  The 'vibe' switch never really worked right which
led to a redesign for v0.3.

### 0.1:  PedalPCB / XC Phase 

I built a few of these with the original XC Phase board from PedalPCB, hand-soldered with
through-hole components. These have only the 'Rate' knob and no 'vibe' switch but still sound
very good.
