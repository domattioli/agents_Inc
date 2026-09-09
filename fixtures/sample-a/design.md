# Pump Controller — Design Note

Requirement R1. The controller shall hold outlet pressure at 3.5 bar plus or minus 0.2 bar.

Requirement R2. Sampling interval shall not exceed 50 milliseconds.

Requirement R3. On sensor fault the controller shall fail safe to pump off within 200 milliseconds.

Assumption A1. Inlet pressure never drops below 1.0 bar; this is not verified against site data.

Interface I1. Setpoint is written over Modbus register 40001 as an unsigned 16-bit value in millibar.
