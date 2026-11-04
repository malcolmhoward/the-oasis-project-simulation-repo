"""
simulation.live — real implementations of HAL interfaces, beside the simulated ones in simulation.layer0-2.

The Provider pattern swaps implementations behind one interface; keeping real implementations in the same package
lets a consumer pick whichever its hardware supports, with a simulation as the fallback.  Nothing here is imported
by ``import simulation``: real sources load platform libraries and are opt-in.

Packages: ``gpu`` (GPU telemetry).
"""
