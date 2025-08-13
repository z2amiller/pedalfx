## Getting started with SMD PCBA(ssembly) at JLCPCB

### Disclaimer
![I have no idea what I'm doing](http://i1.kym-cdn.com/photos/images/original/000/234/739/fa5.jpg)

I'm just some guy who reads/researches stuff to a possibly-unhealthy degree. I don't even play guitar any more and never really did - I make effects for friends and family as a hobby.  I am not a PCB designer or EE by trade.

This guide assumes KiCad for some of the specific tooling, but there's lots of general advice that will be applicable to any CAD software.

This guide mostly focuses on SMD assembly, though I often have mixed SMD/THT boards made at JLC.

This guide also assumes a general familiarity with working with KiCAD or another EDA, as well as some familiarity with SMD package types though you can probably figure that out as you go along if you're new to this.

## Capacitors

### Audio Path

When using SMD components, I use C0G/NP0 caps for anything in the audio path,  Mostly muRata branded caps, since those are a respected brand and are generally available on LCSC/JLC for C0G caps.

Smaller value caps (pF range) tend to be 0603 packages, small-nF in 0805, and >47nF is only available in 1206.  There is some overlap between the ranges (e.g. there are 100pF capacitors in both 0603 and 0805 sizes).

MLCC/SMD C0G capacitors are available up to 220nF in reasonable cost/size packages.  For values bigger than this, I will switch to a through hole box-type film capacitor.  JLC does have a selection of these types of capacitors, and I have had some effects built this way.  I have a big pile of Wima capacitors handy, though, so I'll often just leave the BOM unpopulated for these parts and hand solder them at home.

### Decoupling and other MLCC ceramics

I use X7R and X5R capacitors for decoupling - it's good practice to put a small 100nF/1uF capacitor very near the +VCC input of an IC (op-amp, CD4xxxx, etc).  These can also be useful as the charge capacitors for a charge pump for building 18V or dual-supply effects.

Note that X7R/X5R capacitors lose effective capacitance as the DC voltage increases, and in fact the smaller the package the more pronounced this effect is [citation needed].   Because of this, it can be a good idea to overspec the voltage, I use at least 50V parts for my MLCC capactors.

### Electrolytics

Most of the time, electrolytics are used as 'bulk capacitors' on the power supply to buffer power on the +VCC and VREF lines.  For these, I typically use whatever's cheap and rated at >=2000 hours at 105C.

For stuff in the audio path, I try to use a more 'name-brand' capacitor like Nichicon, Rubycon or [genuine Panaphonics](http://3.bp.blogspot.com/--qod2lsR960/USzEa19KJ0I/AAAAAAAAAbg/6Ongm0cmu2Y/s1600/tumblr_kzgp33zF901qz4gpro1_500.jpg).  Honestly this probably doesn't really matter.  Does box wine have even have a cork?

On some of my designs, I've left the electrolytic caps as through-hole devices that I hand-solder at home to avoid [Extended](#extended-vs-basic) component costs.

## Resistors

Nothing much to say about resistors.  I use the Uni-Royal 0603 resistors in almost all of my designs.

The 0603 resistors have the largest selection of '[Basic](#extended-vs-basic)' parts.  You can also get 0805 or even 1206 resistors but those are progressively more limited.  Or you can go 0402 if you want resistors for ants.  JLC stocks even smaller resistors than this, but you get into [standard assembly](#standard-vs-economic) territory.  0603 seems like a good compromise to me.

## Extended vs Basic

"Basic" parts at JLCPCB are a library of a couple thousand parts that are effectively always loaded in their pick and place machines.  You can use these parts for [Economic](#standard-vs-economic) PCBA for simply the cost of the components.

"Extended" parts are any other parts that are not already loaded in the pick and place feeders.  Each distinct extended part in your bill of materials costs an extra $3 of setup costs in labor for someone to load the feeder.  The capacitors in your BOM might be $0.015, but if it's an extended part it costs $3.015 to place the first one.

There is a 'Basic' checkbox filter on the JLCPCB parts library that filters to only the basic parts.

Through-hole parts are always 'Extended' but do not incur a $3-per-part cost.  The first through-hole part you add to your board costs ~$3.50, but after that, each joint costs ~$0.02.  (So if you have 10 joints and order 10 boards, that's an extra ~$2.00 for the 100 solder joints).

### Playing Extended Part Golf

When ordering PCBA in prototype/hobbyist quantities, the $3-per-component costs add up fast.  When laying out a board, keep the Basic/Extended parts in mind.  With resistors and capacitors you can add these components in series/parallel to add up to 'Basic' values to avoid the extended part cost.  For example, if you already have a 100nF capacitor on the board, you could replace a 47nF capacitor with 2x100nF capacitors in series, or a 22nF capacitor with 10nF+10nF+2.2nF in parallel.

Notably, 2.2nF 0805 C0G capacitors are 'Basic' and very cheap at ~$0.03, so you can use these to build values close to 6.8nF, 10nF, etc, if you're willing to trade the board space for the cost.

This can also be a deciding factor to use a box style film cap - if there's room on the layout, it might be worth it to me to just hand-solder a capacitor if there's just a single capacitor of a certain (hard-to-craft) value.

### Other notable 'Basic' parts

One good thing is that SOP-8 versions of the TL072, NE5532, and LM386 are available as 'Basic' parts at JLC, so you can mix and match op-amps on your design with the op-amp that best meets the need of your effect without extra cost.

Because these are so cheap, sometimes I will add another one to my design as an input or vref voltage buffer, or even to simplify the layout.  They're all less than ~$0.15/ea.

## Standard vs Economic

"Economic" PCBA is much cheaper for small runs, but has more limitations.  Economic PCBA has a small-ish subset of [PCB colors, layers, and finishes](https://jlcpcb.com/capabilities/pcb-assembly-capabilities) - for example if you want a 4-layer Economic assembly, they only make those in green.
There is also a quantity limit on Economic assembly, capping out at 50 boards.  "Economic" PCBA also cannot have V-CUT panelization - you can self-panelize your board but you need to do it manually using "[mouse bites](https://jlcpcb.com/blog/technical-guidance-mouse-bite-panelization-guide)".

On the plus side, "Economic" PCBA has a smaller setup cost ($8), "Basic" parts have no setup costs, and "Extended" parts are $3/ea. 

"Standard" gives the whole range of colors, and you can have JLC panelize your board, or you can self-panelize with either mouse bites or V-cuts.  You have to pay $1.50 for each component, extended or not, and the setup cost is $25.

### Standard PCBA gotchas

I have noticed that there are some components that will trigger 'Standard' PCBA if included.  I have noticed this specifically with some electrolytic capacitors - including one of these types of components will make the whole board ineligible for Economic PCBA.

In the JLC parts search, there's a checkbox to filter on 'Economic' components.   There are very few that I have seen that are standard-only (I suspect something weird about the reels).

## KiCad specific

The [Bouni KiCad Tools](https://github.com/Bouni/kicad-jlcpcb-tools) are really pretty amazing.  Installing this toolset gives you a new 'JLCPCB' button that opens a dialog that lets you search/tag each component in your schematic with the LCSC number.  You can also tag whether or not to include each component in the BOM/CPL files and export these mappings back to the schematic.

Unfortunately the search functionality is broken as of mid-August 2025 due to a downstream change, or a change in the LCSC data format.  Top People are working to fix this.  In the meantime, the search functionality on JLCPCB is still pretty good with parametric search to find the LCSC part numbers for all of the components in your design.

Additionally, this tool has a 'Generate' button, which will automatically create three files:  A gerber.ZIP file, a BOM (bill of materials), and a CPL (component placement) file.

Once you select the PCBA option at JLC, you'll have a screen where you can upload your BOM and CPL, which will then break down the component costs and show you the placement.

Note that sometimes some of the components will be rotated the wrong way on your board!  JLC gives you a UI that lets you fix component rotation issues.  The Bouni tools actually have a rotation manager built in as well that you can use to more permanently fix the rotations so you don't need to fix them in the JLC UI after you upload.

## Off In The Weeds

Here's some other random info that may or may not help that didn't fit in the other sections.

### 2 layer vs 4 layer board

It really is amazing how cheap 4-layer boards are.  In relative costs, it's like $2 vs $7 (special offer) but in the grand scheme of PCBA the marginal cost of a 4-layer board is very small relative to the benefits.  It's much easier to get a clean ground plane on a 4-layer board (usually layer 2, "IN.1") and much easier to distribute +9V and VREF (layer 3, "IN.2") to all of the components wherever they may be, and on a marginally complicated layout it can reduce the amount of time you spend optimizing placement and traces.

On the downside, in addition to the relatively small additional cost, the colors and finishes of the boards are much more limited, so you'll be stuck with green PCBs for 4-layer designs.

### Mixing Through-Hole components

I add some through-hole components to almost every design these days.  I've standardized on 2x 3-pin headers from my footswitch breakout, so I'll include the JST "PH" style headers on all of my designs, and just pay the extra ~$4 to have those soldered on.  Then I can just use pre-made 22 gauge PH connectors to hook everything up instead of screwing around with soldering wires to things.  I know people love the look of the honkin' romex-lookin 14 gauge solid wire routing in their pedals but that sucker goes right into a 0.5mm x 0.035mm PCB trace so what's the point.

Trimpots are another place where I've found it worthwhile to have them soldered by JLC, since many effects pedals have a trimpot for adjusting bias.

### More Price Hacking: JLC Parts Library

Another trick I've recently started using to keep prices down is to use the JLC 'My Parts' library. How much this helps depends on how many boards you buy and what kind of quantities you buy them in.

You can pre-purchase items, and have JLC 'hold' them in a personal inventory. I imagine that in practice these don't actually get put in a dedicated inventory, but it gives JLC an idea of the minimum quantity of items to have on hand. The nice thing here is that you can take advantage of the quantity price breaks on parts that you use in multiple designs, or in the same design across multiple orders. The op-amps and C0G capacitors which are (relatively) expensive per-part might be 20-50% cheaper if you hit one of the quantity price breaks. As an example, the LM137000 from TI are ~$0.65/each for qty 1, but ~$0.45 for qty 30+. So if you think you'll be using a lot of a particular part now and in the future, it can make sense to pre-purchase these and 'draw down' the quantity as you use them.

For things like electrolytics I've found that it helps because there are just so damn many to choose from. I'll just find one that works and put it in my parts library and that effectively 'bookmarks' it for me and makes it easy to choose which of the 348 different 100uF 35V caps to use.

JLC will automatically use parts out of your inventory first. They'll then dip into 'normal' inventory if you stock yourself out. I'm not sure how the pricing works for this, I haven't managed to do it yet, but I imagine it goes back to standard quantity pricing after you've stocked out.

Obviously this only saves you money if you use up all of the stock you buy. If you decide you don't need a particular item any more, you can resell it, though. You'll notice on some parts when you are buying them that there is an 'Idle Parts' inventory. This is from other users on JLC reselling items that they've already purchased from their own (virtual) inventory.

You don't pay tariffs when you buy the items for your personal inventory -- only when they get used in a design and shipped to you. You pay the tariff on the price-per-part that you originally purchased the component.
