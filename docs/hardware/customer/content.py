# -*- coding: utf-8 -*-
"""
Single source of truth for the VX-0057 customer Product & Safety Guide.

Both the HTML/PDF builder and the DOCX builder import this module, so the two
deliverables never diverge. Content here is CUSTOMER-FACING ONLY: distilled from
the internal hardware review with all internal detail removed (no part numbers,
net names, GPIO assignments, jumper reference designators, schematic-revision
notes, bench config, or "items to verify"). No regulatory certification is
claimed that has not been verified — see COMPLIANCE.
"""

# ---- document control ----------------------------------------------------
META = {
    "manufacturer": "Viaanix",
    "model": "VX-0057",
    "product": "RTU Board",
    "subtitle": "Universal Cellular / LoRaWAN Telemetry & Remote-I/O Controller",
    "doc_no": "DOC-VX0057-PSG",
    "revision": "A",
    "date": "2026-06-12",
    "tagline": "One platform for Tank Monitor, Callbox, and RTU field applications.",
    "copyright": "© 2026 Viaanix. All rights reserved. Information subject to change without notice.",
}

# ---- product overview ----------------------------------------------------
OVERVIEW = (
    "The Viaanix VX-0057 is a universal industrial telemetry and remote-I/O "
    "controller. A single board combines multi-network connectivity — LTE Cat-1 "
    "cellular with built-in GPS, long-range LoRaWAN, and Bluetooth Low Energy — "
    "with a complete set of field interfaces: optically isolated digital inputs, "
    "4–20 mA and 0–10 V analog inputs, dry-contact relay outputs, high-current "
    "switched outputs for sirens and warning lights, and RS-232 / RS-485 serial. "
    "The same hardware can be deployed as a Tank Monitor, a Callbox, or a full "
    "Remote Terminal Unit (RTU), reporting securely to the VX Olympus cloud "
    "platform. A wide-range DC input, automatic battery failover, and switchable "
    "sensor power make the VX-0057 ready for demanding, always-on field service."
)

# ---- key features (grouped) ----------------------------------------------
FEATURES = [
    ("Connectivity", [
        "LTE Cat-1 cellular (North America bands) with integrated GPS / GNSS",
        "LoRaWAN long-range radio for the 915 MHz (US) ISM band",
        "Bluetooth Low Energy 5.3 / IEEE 802.15.4 (2.4 GHz)",
        "Secure check-in to the VX Olympus cloud platform",
    ]),
    ("Field I/O", [
        "4 × optically isolated digital inputs",
        "4 × 4–20 mA analog inputs with selectable loop power",
        "1 × 0–10 V analog input",
        "4 × SPDT dry-contact relay outputs",
        "2 × 12 V high-side switched outputs (siren / warning light)",
        "RS-232 and RS-485 (half- or full-duplex) serial ports",
        "Switchable 5 / 12 / 24 V sensor port power",
    ]),
    ("Power & Platform", [
        "Wide 5–32 V DC input (nominal 12.0–13.8 V)",
        "External 12 V battery input with automatic, glitch-free failover",
        "Works with an optional external UPS / battery-charger module",
        "16 MB onboard storage for local data logging",
        "Dual-core 32-bit Arm® Cortex®-M33 processor",
    ]),
]

# ---- specifications (label, value) ---------------------------------------
SPECS = [
    ("Processor", "Dual-core 32-bit Arm® Cortex®-M33 wireless MCU"),
    ("Cellular", "LTE Cat-1, North America bands; integrated GNSS (GPS); micro-SIM socket"),
    ("LoRa", "915 MHz, US ISM band (902–928 MHz)"),
    ("Bluetooth / 802.15.4", "Bluetooth LE 5.3 / IEEE 802.15.4, 2.4 GHz"),
    ("Digital inputs", "4 × optically isolated; common or isolated ground"),
    ("Analog inputs", "4 × 4–20 mA (selectable 12 / 24 V loop power) + 1 × 0–10 V"),
    ("Relay outputs", "4 × SPDT dry contact (COM / NO / NC)"),
    ("Switched outputs", "2 × high-side 12 V switched outputs for siren / warning light"),
    ("Serial ports", "1 × RS-232; 1 × RS-485 (half- or full-duplex)"),
    ("Sensor port power", "Switchable 5 / 12 / 24 V"),
    ("Local storage", "16 MB onboard flash for data logging"),
    ("Input voltage", "5–32 V DC (nominal 12.0–13.8 V)"),
    ("Backup power", "12 V battery input with automatic failover; supports an optional external UPS / charger"),
    ("Antenna connectors", "Cellular (with GPS), LoRa, and Bluetooth; connector type varies by unit — see product label"),
    ("Cloud platform", "VX Olympus cloud platform"),
    ("Mechanical / environmental", "See product label; contact Viaanix for the deployment datasheet"),
]

# ---- field interfaces at a glance (function, qty, notes) -----------------
IO_TABLE = [
    ("Digital input", "4", "Optically isolated; selectable common or isolated ground"),
    ("4–20 mA analog input", "4", "Selectable 12 V / 24 V loop power for 2-wire transmitters"),
    ("0–10 V analog input", "1", "Low standby power"),
    ("Relay output", "4", "SPDT dry contact (COM / NO / NC)"),
    ("Switched output", "2", "12 V high-side, for siren / warning light"),
    ("RS-485 serial", "1", "Half- or full-duplex"),
    ("RS-232 serial", "1", "Standard serial port"),
]

# ---- safety symbol legend (icon, term, meaning) --------------------------
SYMBOLS = [
    ("alert", "Safety alert", "Indicates a personal-injury hazard. Read the message that follows."),
    ("electric", "Electric shock", "Risk of electric shock from hazardous voltage."),
    ("hot", "Hot surface", "Surfaces may be hot during and after operation."),
    ("esd", "ESD-sensitive", "Static-sensitive device — observe ESD precautions before handling."),
    ("rf", "RF energy", "Device contains radio transmitters. Keep clear of antennas when transmitting."),
    ("battery_w", "Battery hazard", "Risk of fire, venting, or explosion from improper battery use or charging."),
    ("ground", "Protective earth", "Connect to protective earth / ground as instructed."),
    ("book", "Read the guide", "Refer to this guide before installing, operating, or servicing."),
    ("recycle", "Recycle", "Do not discard with household waste. Recycle electronics per your region's regulations."),
]

# ---- ANSI Z535 hazard panels ---------------------------------------------
# level drives the colour band; icon is the left pictogram.
HAZARDS = [
    {
        "level": "DANGER", "icon": "electric", "title": "AC Mains — Risk of Electric Shock or Death",
        "text": "When the optional AC mains / UPS input is used, the AC terminals carry "
                "lethal line voltage. Disconnect and lock out ALL power sources before "
                "opening the enclosure or servicing. AC connection and servicing must be "
                "performed only by a qualified electrician, in accordance with local "
                "electrical codes. Do not energize AC mains on a bench or test setup.",
    },
    {
        "level": "WARNING", "icon": "electric", "title": "Relay & Output Terminals May Switch Hazardous Energy",
        "text": "Circuits connected to the relay terminals (COM / NO / NC) and to the "
                "siren / light outputs may carry hazardous voltage or current. De-energize "
                "external circuits before wiring. Do not exceed the contact and output "
                "ratings marked on the product or stated in the deployment datasheet.",
    },
    {
        "level": "WARNING", "icon": "battery_w", "title": "Battery Hazard — Fire, Venting, or Explosion",
        "text": "Use only the specified battery type, voltage, and polarity. Reverse "
                "polarity, short circuits, over-charging, or over-current can cause "
                "leakage, venting, fire, or explosion. Keep the input fuse in place, "
                "observe correct polarity, provide appropriate over-current protection, "
                "and follow the battery manufacturer's handling and charging instructions. "
                "Do not short-circuit or incinerate batteries.",
    },
    {
        "level": "CAUTION", "icon": "rf", "title": "Radio-Frequency Exposure",
        "text": "This product contains radio transmitters (cellular, LoRa, and Bluetooth). "
                "To limit RF exposure, connect the antennas and maintain the antenna "
                "separation distance specified for your installation, and do not operate "
                "with personnel in close proximity to the antennas while transmitting. "
                "Follow all applicable RF-exposure requirements for the host installation.",
    },
    {
        "level": "CAUTION", "icon": "hot", "title": "Hot Surfaces During Operation",
        "text": "Power-conversion and switched-output components can become hot during "
                "normal operation. Allow the board to cool before handling and provide "
                "adequate ventilation within the enclosure. In normal use these components "
                "are inside the host enclosure and are not user-accessible.",
    },
    {
        "level": "NOTICE", "icon": "notice", "title": "Correct Supply Voltage & Polarity",
        "text": "Applying reverse polarity or a voltage outside the 5–32 V DC input range "
                "can damage the unit. Confirm the supply voltage and polarity, and ensure "
                "the source provides adequate current, before applying power.",
    },
    {
        "level": "NOTICE", "icon": "esd", "title": "Static-Sensitive Components",
        "text": "This product contains static-sensitive electronic components. Handle the "
                "board only by its edges in an ESD-safe environment, using a grounded wrist "
                "strap and mat. Electrostatic discharge can cause latent damage that is not "
                "visible at installation.",
    },
    {
        "level": "NOTICE", "icon": "notice", "title": "Connect Antennas Before Transmitting",
        "text": "Do not operate the cellular, LoRa, or Bluetooth transmitters without the "
                "correct antenna connected — running a transmitter without a proper antenna "
                "load can damage the radio. Connect the antenna supplied or specified for "
                "your unit to each radio before enabling it.",
    },
    {
        "level": "NOTICE", "icon": "notice", "title": "Suitable Enclosure & Environment",
        "text": "Install the board in an enclosure appropriate to the environment. Protect "
                "it from water ingress, condensation, conductive dust, vibration, and "
                "direct sunlight unless the deployment is specifically rated for those "
                "conditions.",
    },
]

# ---- handling / installation guidance (icon, heading, paragraphs) --------
HANDLING = [
    ("book", "Before You Begin",
     ["Read and understand this entire guide before installing, operating, or "
      "servicing the VX-0057. Installation and service should be carried out by "
      "qualified personnel familiar with electronic equipment and local codes. "
      "Keep this guide with the equipment for future reference."]),
    ("esd", "ESD Handling",
     ["The VX-0057 is an electrostatic-sensitive assembly. Before handling, "
      "discharge static by using a grounded wrist strap and an anti-static mat. "
      "Handle the board by its edges, avoid touching connector pins and components, "
      "and store or transport the board in anti-static packaging."]),
    ("alert", "Mounting & Environment",
     ["Mount the board securely inside a suitable enclosure, leaving clearance for "
      "wiring, antennas, and ventilation. Avoid mounting over heat sources or where "
      "water, condensation, or conductive dust can reach the electronics. Route field "
      "wiring and antenna cables so they are strain-relieved and cannot chafe."]),
    ("ground", "Power & Wiring",
     ["Supply the board from a clean 5–32 V DC source (nominally 12.0–13.8 V) with "
      "correct polarity. Keep the input fuse in place and provide branch-circuit / "
      "over-current protection suited to the installation. Connect protective earth / "
      "ground where indicated. Do not apply AC mains directly to the DC input."]),
    ("rf", "Antennas, SIM & Radios",
     ["Connect the antenna supplied or specified for your unit to each radio before "
      "enabling its transmitter (cellular, GPS, LoRa, and Bluetooth). Insert an "
      "activated SIM for cellular service. Maintain a safe separation distance from "
      "the antennas while the device is transmitting (see RF Exposure)."]),
    ("alert", "Field I/O Wiring",
     ["Observe the marked ratings for relay contacts, switched outputs, and analog "
      "loop power. De-energize external circuits before connecting them. The digital "
      "inputs can be wired for common or isolated ground; the 4–20 mA channels can "
      "supply 12 V or 24 V loop power to 2-wire transmitters as configured."]),
    ("rf", "RF Exposure",
     ["This product contains radio transmitters. During normal operation, maintain "
      "the antenna separation distance specified for the installation and do not "
      "operate with personnel in close proximity to the antennas. Follow all "
      "applicable RF-exposure guidance for the host installation."]),
    ("wrench", "Service & Maintenance",
     ["There are no user-serviceable internal components. Before servicing, "
      "disconnect and lock out all power sources (DC, battery, and AC mains where "
      "fitted) and allow the board to cool. Refer all repair to qualified personnel "
      "or to Viaanix."]),
    ("recycle", "Storage, Transport & Disposal",
     ["Store and transport the board in anti-static packaging within the rated "
      "environment. At end of life, do not discard the product with general or "
      "household waste — recycle it in accordance with the electronics-recycling "
      "regulations applicable in your region (for example, WEEE in the EU), and "
      "dispose of any batteries separately and appropriately."]),
]

# ---- compliance (honest; no unverified certifications claimed) -----------
COMPLIANCE = (
    "The VX-0057 integrates radio modules that are intended to be operated under their "
    "respective regulatory approvals. Where such approvals apply, the corresponding "
    "regulatory markings and identifiers (for example, FCC ID / IC numbers, and any "
    "safety or regional conformity marking) are shown on the product label of each unit. "
    "Confirm the markings on your specific unit and refer to the product label and "
    "accompanying Viaanix documentation for the conditions of authorized operation. This "
    "document is product information for reference only and does not by itself constitute "
    "a certification, listing, or declaration of conformity."
)

READ_FIRST = (
    "Read and understand this entire document before installing, operating, or "
    "servicing this product. Failure to follow these instructions could result in "
    "serious injury, death, or equipment damage. Keep this document for future reference."
)

# ANSI Z535.4 signal-word colours
HAZARD_COLORS = {
    "DANGER":  {"bg": "#C8102E", "fg": "#FFFFFF"},  # safety red
    "WARNING": {"bg": "#EF7100", "fg": "#000000"},  # safety orange
    "CAUTION": {"bg": "#FFD200", "fg": "#000000"},  # safety yellow
    "NOTICE":  {"bg": "#005EB8", "fg": "#FFFFFF"},  # safety blue
}
