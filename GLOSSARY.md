# Glossary

Terminology used in the E.C.H.O. simulation framework. Entries are alphabetical.

---

**ABC (Abstract Base Class)**
A Python class (from the `abc` module) that defines an interface contract. ABCs cannot be instantiated directly — subclasses must implement all abstract methods. In this project, ABCs define the HAL interfaces that mock implementations conform to.

**BCM (Broadcom SOC Channel)**
A GPIO pin numbering scheme that uses the Broadcom chip's internal channel numbers. One of two numbering modes supported by the RPi.GPIO library (the other being BOARD).

**BOARD (Physical Pin Numbering)**
A GPIO pin numbering scheme that uses the physical pin positions on the Raspberry Pi header. One of two numbering modes supported by the RPi.GPIO library (the other being BCM).

**DAP2 (Dawn Audio Protocol 2.0)**
A WebSocket-based protocol for distributed voice assistants in the D.A.W.N. ecosystem. Enables "smart satellites" — remote devices that run speech pipeline locally and send text queries to the central D.A.W.N. daemon.

**GPIO (General-Purpose Input/Output)**
Digital pins on a microcontroller or single-board computer that can be configured as either input or output. Used by S.P.A.R.K. for controlling actuators and reading digital sensors.

**GPS (Global Positioning System)**
A satellite-based navigation system that provides location and time information. M.I.R.A.G.E. and A.U.R.A. use GPS data for position tracking.

**HAL (Hardware Abstraction Layer)**
A set of interface contracts that decouple application code from specific hardware implementations. In E.C.H.O., the HAL defines abstract interfaces (in `simulation/hal/`) that both Python mock implementations and future C implementations must conform to.

**I2C (Inter-Integrated Circuit)**
A two-wire serial communication bus used to connect low-speed peripherals (sensors, displays, EEPROMs) to a microcontroller. Pronounced "I-squared-C" or "I-two-C". A.U.R.A. uses I2C for environmental sensor communication.

**IMU (Inertial Measurement Unit)**
A sensor package that measures acceleration, rotation, and sometimes magnetic field. Provides heading, pitch, and roll values. Used by M.I.R.A.G.E. for helmet orientation tracking.

**LWT (Last Will and Testament)**
An MQTT feature where a client registers a message with the broker at connect time. If the client disconnects unexpectedly, the broker publishes this message on the client's behalf — used for offline status detection in OCP.

**MQTT (Message Queuing Telemetry Transport)**
A lightweight publish-subscribe messaging protocol used for inter-component communication in O.A.S.I.S. Components publish and subscribe to topics (e.g., `hud/status`, `aura`) via an MQTT broker.

**OCP (OASIS Communications Protocol)**
The standardized messaging protocol used across O.A.S.I.S. components over MQTT. Defines status messages, discovery, command/response patterns, and keepalive heartbeats.

**PCM (Pulse-Code Modulation)**
A method for digitally representing analog audio signals. Raw audio data in E.C.H.O. is represented as 16-bit signed PCM samples — the standard format used by audio hardware and libraries.

**SPI (Serial Peripheral Interface)**
A synchronous serial communication bus used for short-distance communication between a microcontroller and peripherals. Faster than I2C but requires more wires (MOSI, MISO, SCLK, CS). S.P.A.R.K. uses SPI for high-speed sensor data.

**VAD (Voice Activity Detection)**
An algorithm that determines whether an audio signal contains human speech. Used by D.A.W.N. satellites to detect when a user has stopped speaking, triggering the end of a voice command.
