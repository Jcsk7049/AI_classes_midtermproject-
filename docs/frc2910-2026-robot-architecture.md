# FRC Team 2910 — 2026 Competition Robot: Architecture Breakdown

A read-through of [`FRCTeam2910/2026CompetitionRobot-Public`](https://github.com/FRCTeam2910/2026CompetitionRobot-Public),
Team 2910's robot code for the 2026 FRC game **REBUILT**.

The upstream repository was archived read-only on **June 10, 2026**, and contains a single
commit ("Initial commit") — it is a code drop of the season's work, not a development history.
Everything below is derived from reading the source at that commit.

- **Scale:** 65 Java files, ~9,000 lines under `src/main/java/org/frc2910/robot/`
- **Language / toolchain:** Java 17, Gradle 8.14.3, GradleRIO 2026.2.1
- **Licensing:** MIT + GPL-3.0, with acknowledgments to AdvantageKit and FRC Teams 254 and 6328

---

## 1. Dependencies and build tooling

| Vendor dep | Version | Role |
|---|---|---|
| CTRE Phoenix 6 | 26.1.3 | TalonFX motors, CANcoder, Pigeon 2, **CTRE swerve API** |
| AdvantageKit | 26.0.0 | `LoggedRobot`, `@AutoLog` IO inputs, WPILOG/NT publishing, replay |
| PathPlannerLib | 2026.1.2 | Trajectory types + `RobotConfig` |
| maple-sim | 0.4.0-beta | Physics simulation of the drivetrain and game pieces |
| BLine-Lib | 0.8.4 | (declared) |
| WPILib New Commands | 1.0.0 | Command-based scheduler |

Build-side quality tooling is unusually thorough for a team codebase:

- **Spotless** + **palantir-java-format**, wired as `compileJava.dependsOn(spotlessApply)` — formatting
  is applied automatically on every build rather than merely checked.
- **Error Prone** 2.39.0 on `compileJava`, with generated code excluded.
- **gversion** generates a `BuildInfo` class (git SHA, branch, build date, dirty flag) that
  `Robot.initLogging()` records as log metadata — so every log file is traceable to an exact commit.
- Fat-jar packaging, `replayWatch` task for AdvantageKit log replay, desktop simulation enabled.

---

## 2. Runtime structure

```
Main
 └─ Robot                    (extends LoggedRobot — lifecycle, logging, dashboards)
     ├─ ConditionalCallbackManager   (gated debug/telemetry callbacks)
     ├─ AutoChooser                  (SendableChooser<Auto>, per-alliance command cache)
     └─ RobotContainer               (owns everything else)
         ├─ RobotConfiguration       (selected by RobotIdentity)
         ├─ RobotState               (shared pose / speeds / vision blackboard)
         ├─ SwerveSubsystem          ← built FIRST, deliberately
         ├─ IntakeSubsystem
         ├─ ShooterSubsystem  ("Serpentine")  ├─ HoodSubsystem
         │                                    └─ FlywheelSubsystem
         ├─ HopperSubsystem
         ├─ SuperStructure           (coordinates all of the above)
         └─ VisionSubsystem          (N × VisionIOLimelight)
```

### `Robot`

Thin by design. Three things stand out:

1. **Watchdog defeat.** `robotInit()` uses reflection to reach the private `m_watchdog` fields on
   `IterativeRobotBase` and `CommandScheduler` and pushes both timeouts to **67 ms**. This suppresses
   loop-overrun spam — a pragmatic call that trades an early-warning signal for a quiet console.
2. **Ordering discipline.** `robotPeriodic()` refreshes all CTRE status signals *before*
   `CommandScheduler.run()`, so every subsystem's `periodic()` in a given cycle sees the same
   consistent snapshot of hardware state. `callbackManager.periodic()` runs *last*, after subsystems
   have populated their inputs.
3. **CAN bus health logging.** On real hardware, CANivore utilization, bus-off count, and TX/RX error
   counts are written to the Phoenix signal log every cycle.

### `RobotContainer`

Constructs subsystems and wires the single Xbox controller. A comment marks a real ordering
dependency:

> `SwerveSubsystem` needs to be built first so that it can update the robot pose from CTRE's pose
> estimator before other subsystems run. While this isn't part of the `CommandScheduler` contract,
> this is the scheduler behavior in 2026.

That is an honest note: the code depends on registration-order execution that WPILib does not
formally guarantee.

---

## 3. The dominant pattern: two-layer state machines

Nearly every subsystem — and the `SuperStructure` itself — implements the same shape:

```java
public enum WantedState  { /* what callers request  */ }
private enum SystemState { /* what the robot is doing */ }

@Override
public void periodic() {
    systemState = handleStateTransition();   // pure mapping + guards
    Logger.recordOutput(".../WantedState", wantedState);
    Logger.recordOutput(".../SystemState", systemState);
    applyStates();                           // side effects only
}
```

The value of the split is that `handleStateTransition()` can refuse a request. `HoodSubsystem` and
`IntakeSubsystem` both force `SystemState.HOMING` whenever `!isHomed`, regardless of what was asked —
the mechanism cannot be commanded to a position it hasn't yet calibrated. `SwerveSubsystem` uses the
same hook to self-terminate: `FOLLOW_PATH` checks endpoint distance and elapsed time each cycle and
rewrites its own `wantedState` to `IDLE` when either condition is met.

Because both enums are logged every cycle, an AdvantageScope log shows exactly what was requested
versus what happened — the single most useful debugging property of this design.

---

## 4. `SuperStructure` — the coordination layer

`SuperStructure` (685 lines) holds no hardware. It reads `RobotState`, computes shot parameters, and
drives the four mechanism subsystems plus the swerve into consistent combinations.

**States:** `STOPPED`, `DEFAULT_STATE`, `HOME`, `SCORE_ON_MOVE`, `SCORE_WITHOUT_OBSERVATION`,
`SCORE_KNOWN_TRANSLATION`, `PASS`, `PASS_MANUAL_ROT`, plus auto-only `AUTO_PASS`, `AUTO_SCORE`,
`AUTO_SCORE_STATIONARY`, and `SYS_ID`.

Each cycle it caches pose, alliance-correct hub translation, field-relative chassis speeds, speed
magnitude, and distance-to-hub once, then dispatches.

### Shooting

The core scoring loop (`scoringOnTheMove`) is:

1. `targetRotation = hub - robotTranslation`, as an angle.
2. Look up flywheel RPM and hood angle from `ShooterInterpolation` (an `InterpolatingDoubleTreeMap`
   keyed on distance: 1.3 m → 2100 RPM / 0°, out to 5.0 m → 2900 RPM / 28°).
3. Scale RPM by an operator-dashboard multiplier (`RPM Percent Adder`, −10 % to +50 %) so the drive
   team can trim on the fly without a code push.
4. Request the swerve into rotation-lock with **limited translation** — the driver keeps translation
   authority, scaled by `SOTM_TRANSLATION_SCALAR = 1.0` for scoring, `0.3` for passing.
5. Fire only when `isReadyToScore()` passes.

`isReadyToScore()` requires: correct superstate, shooter at shot conditions, distance ≥ 1.5 m,
heading within 4°, chassis speed ≤ 0.15 m/s, and (optionally) a live AprilTag observation. Every one
of those predicates is logged individually under `SuperStructure/ShotConditions/*`, so a "why didn't
it shoot" question is answerable from the log alone.

An `ignoreShootingTolerances` escape hatch, bound to a controller paddle, bypasses the entire
tolerance stack — the manual override for when the sensors disagree with reality mid-match.

### Passing

Passing adds **lead compensation**: `getExtrapolatedTranslation(t)` projects the robot forward by
`velocity × time-of-flight` (from `PassingInterpolation`) and aims from the *projected* position, not
the current one. The code is candid about its limits:

> The method for extrapolating the translation … takes the current velocity and multiplies it by the
> time and assumes a straight line path. It doesn't take into account robot acceleration/deceleration
> nor path curvature. We can do better if needed.

### Failsafes

`SCORE_KNOWN_TRANSLATION` is the interesting one. If vision has failed, the operator picks one of
four surveyed field spots (`LEFT_TRENCH`, `RIGHT_TRENCH`, `LEFT_UPRIGHT`, `RIGHT_UPRIGHT`) on the
D-pad, drives the robot physically to that spot, and the code *asserts* the robot is there —
`swerveSubsystem.resetTranslation(knownTranslation)` — then shoots the solution for that distance.
A degraded but usable scoring mode built on the assumption that the drive team can position by eye.

---

## 5. `SwerveSubsystem` — the largest single class (927 lines)

Fourteen `WantedState` values: teleop, three SysId variants, seek, path-following, two rotation-lock
flavors, anti-defense wheel lock, drive-to-point, target tracking, module positioning, stator-limit
setting, and idle.

**Teleop input conditioning** (`getChassisSpeedsFromJoysticks`) is a clean four-step pipeline:
deadband (0.1) → sign-preserving square for fine low-speed control → scale by max velocity with an
alliance flip → **skew compensation**, offsetting the heading used for the field→robot transform by
`yawRate × −0.03` to cancel the drift a swerve accumulates while translating and rotating together.
That compensation is applied only on real hardware (`Robot.isReal()`), since the sim has no such
error to cancel.

**Drive-to-point** is a scalar PID on straight-line distance-to-target (kP 3.0 auto / 3.6 teleop,
kD 0.1), decomposed into x/y by the direction of travel, with a static-friction floor of 2 % of max
velocity added whenever the robot is more than half an inch out. Heading is handled separately by
CTRE's `FieldCentricFacingAngle`. This is the primitive the autos are built from — not trajectory
following.

**"Seeking wheelchair" mode** is a nice piece of driver ergonomics: instead of letting the driver
strafe, the right stick sets a *heading*, and translation is emitted along the robot's current
(reversed) heading. The robot points its intake where you push and drives that way — no strafing,
which matters when you are trying to sweep a line of game pieces.

**Allocation discipline.** Every `SwerveRequest` (teleop, idle, brake, drive-at-angle,
continuous-tracking) is pre-allocated as a field and mutated with `withX()` builders rather than
constructed per cycle. `CHASSIS_SPEEDS_ZERO` is a shared constant. This is deliberate GC-pressure
avoidance on a 20 ms loop.

---

## 6. Mechanism base classes

`subsystems/base/` is a small framework the mechanisms are assembled from:

- **`ServoMotorSubsystem`** — position-controlled mechanisms with travel limits. Wraps Motion Magic,
  soft limits, and a `home()` routine that disables soft limits, drives at a fixed duty cycle until
  velocity stays under a threshold for a settle time, zeroes the encoder to a caller-supplied
  position, then restores the original limit configuration. In simulation it short-circuits to
  "already homed."
- **`RollerMotorSubsystem`** — velocity/voltage-controlled mechanisms with no position limits.
- **`ServoWithFollowersSubsystem` / `RollerWithFollowersSubsystem`** — leader/follower groups where
  followers are wired via CTRE `Follower` control and their inputs are logged separately.
- **`ServoWithFusedCanCoderSubsystem`** — absolute-encoder-fused positioning.
- **`MotorIO`** / **`MotorIOTalonFX`** / **`SimMotorIOTalonFX`** — the hardware seam.

Every public API call on these base classes logs its argument under `<MotorName>/API/<method>/<arg>`.
That means a log replay reconstructs not just what the sensors read but every command issued —
which is what makes AdvantageKit's deterministic replay actually useful here.

The concrete mechanisms are thin on top:

| Subsystem | Composition | Notes |
|---|---|---|
| `IntakeSubsystem` | servo deploy + 2 rollers | Deploy 114.3°, retract 10° (compresses fuel in the hopper), rollers at 100 % intaking / 15 % retracting |
| `HoodSubsystem` | servo | 0–37°, homes to −0.139° against a hard stop |
| `FlywheelSubsystem` | roller + followers | RPM setpoint ÷ 60 → rotations/sec |
| `ShooterSubsystem` ("Serpentine") | hood + flywheel | `isAtShotConditions() = hood at position && flywheel at RPM` |
| `HopperSubsystem` | 4 rollers + 2 CANrange sensors | Auto-preloads at 7 % duty when the hopper is full but the feeder is empty; 100 % when shooting |

The hopper's preload logic is the subtlest bit of mechanism code in the repo: a `Debouncer`
(0.25 s, rising) on the hopper range sensor prevents a single game piece bouncing past the sensor
from triggering a feed, and the preload only runs when the *feeder* sensor is clear — so fuel is
staged one piece deep at the shooter without jamming it.

---

## 7. Hardware abstraction and configuration

```
RobotIdentity.get()  →  RobotConfiguration.getRobotConfiguration(identity)  →  ReBlitz
```

`RobotIdentity` returns `SIMULATION` when not on real hardware, otherwise looks up the RoboRIO serial
number in an identity map and falls back to `REBLITZ`. (In the shipped code that map is
`Collections.emptyMap()`, so the lookup always falls through — the mechanism is present but only one
physical robot was ever configured.)

`RobotConfiguration` is an interface exposing swerve constants, module constants, camera configs, and
per-mechanism configs. `ReBlitz` (574 lines) is the single implementation and holds every CAN ID,
gear ratio, current limit, PID gain, and CANcoder offset in one place. Notable hardware facts
recorded there: MK4i L3 modules, 2" wheel radius, 22.25" × 21.75" wheelbase, Kraken X60 drive
(observed max 4.96 m/s, not the theoretical value), Pigeon 2 on a CANivore.

The IO seam is used consistently — `RobotContainer` picks `MotorIOTalonFX` vs `SimMotorIOTalonFX`
and `SwerveIOCTRE` vs `SwerveIOSim` at construction, and no subsystem knows which it got. The cost
is that each of the four `build*Subsystem()` methods in `RobotContainer` is a near-duplicated
if/else where only the IO class name differs.

---

## 8. Vision

Deliberately *not* a pose estimator. `VisionIOLimelight` reads raw Limelight NetworkTables entries
(`tv`, `tx`, `tid`, `tcornxy`) and computes distance itself: it takes the four target corners, sorts
them by x, averages the left and right edge pixel heights, and feeds that pixel height through a
`VisionInterpolation` table to get meters. Robot pose is then reconstructed trigonometrically from
the known tag pose, that distance, and the gyro heading.

A `txScalarValue` per camera corrects a measured non-linearity — the comment explains that Limelight
`tx` and Pigeon 2 yaw were observed not to scale at the same rate, so the ratio is applied to `tx`.

`SuperStructure` consumes observations by calling `swerveSubsystem.resetTranslation(...)` — a hard
snap of translation only, preserving heading. The code flags this itself:

> **TODO:** Improve how we relocalize for every valid vision target detected. There's an issue with
> this approach as it doesn't compensate for the latency between when the vision pose was estimated
> and how far the robot has moved since. Fusing vision in a pose estimator would help…

A `visionObservationLatch` is used during scoring so that once a tag has been seen during a
scoring attempt, the shot stays authorized even if the tag drops out mid-sequence.

---

## 9. Autonomous

`AutoChooser extends SendableChooser<Auto>` with a per-alliance cache. `AutoFactory` is instantiated
once per alliance, and each `(alliance, auto)` pair is built lazily during `disabledPeriodic()` and
cached as a `Pair<Pose2d, Command>` — so command construction (including
`RobotConfig.fromGUISettings()` I/O) never happens during a match, and the operator dashboard can
display and reset the selected starting pose while disabled.

Shipped routines: `LEFT_NEUTRAL_ZONE`, `RIGHT_NEUTRAL_ZONE`, `LEFT_NEUTRAL_ZONE_TO_DEPOT`, `DEPOT`,
plus `IDLE`, `TEST`, and three SysId programs behind a compile-time flag.

The routines are built almost entirely from `driveToPoint` / `driveToPointWhileIntaking` composed
with `Commands.sequence`, each waypoint carrying its own velocity cap and position tolerance — the
tolerance is the tuning knob that lets the robot "flow" through a sweep instead of settling at each
point. Deliberately loose tolerances (2.5–3.5 m) on sweep entries mean those waypoints act as
direction hints rather than destinations. Scoring is punctuated by `scoreStationary()`, which is
raced against a 4-second timeout so a failed shot can never stall the routine.

Path following via PathPlanner trajectories exists (`WantedState.FOLLOW_PATH`,
`followPathPlannerTrajectory`) but is not used by any shipped auto, and its three correction PID
controllers are all constructed with zero gains — meaning that path would run pure feedforward if
invoked. Choreo support is present only as commented-out fields.

---

## 10. Performance and logging techniques worth stealing

These are the parts of the codebase most transferable to other projects:

**`StatusSignalRefresher`** — a singleton that collects every CTRE `StatusSignal` in the robot and
refreshes them in one batched `StatusSignal.refreshAll()` per loop. It supports per-signal *delay
counts* (refresh every loop / every other loop / every third…), and `finalizeStatusSignals()`
precomputes, for each cycle index, the exact array of signals due that cycle. Those arrays are built
once and reused, so the hot path is a map lookup plus one batch call — no per-cycle allocation. This
is the single biggest CAN-bandwidth optimization in the project.

**`ConditionalCallbackManager`** — verbose debug logging is registered as callbacks and only
executed when a Shuffleboard toggle is on. The toggle's label is honest about the tradeoff:
`"Debug Logging (WARN: Loop Overruns)"`. `MotorIOTalonFX.updateInputs()` splits its work across the
gate — position/velocity always update, while current/voltage/temperature/acceleration only update
when debug is enabled.

**`DelayedBatchSignalLogger`** — motor-name metadata writes are collected and flushed once, 10
seconds after the first request, via a scheduled command that runs while disabled. This keeps dozens
of one-time string writes out of robot startup.

**`LoggedTunableNumber`** (from Team 6328, credited in-file) — dashboard-tunable constants that
compile down to plain default values when `Constants.tuningMode` is false, so tuning infrastructure
costs nothing in competition builds.

**SysId integration** — translation, steer, and rotation characterization routines are wired as
selectable autonomous programs, with `createPrepareForSysIdCommand` first disabling vision updates
and physically aligning the modules (straight for translation/steer, 45°-X for rotation) before
the quasistatic/dynamic sweeps run.

---

## 11. Rough edges

Read honestly, this is an in-season codebase with the marks of one. Things a reader should not
mistake for intent:

- **`FLYWHEEL_RPM_TOLERANCE = 3000.0`.** Against setpoints of 2100–2900 RPM, this makes
  `isShooterAtTargetRPM()` effectively always true. Whether that is a deliberate "flywheel readiness
  isn't the binding constraint" decision or a debugging value left in, it means the RPM gate in
  `isAtShotConditions()` does nothing.
- **`SuperStructure.maxVelocityForAuto` is declared but never assigned** — it stays `0.0`. It is read
  by `autoScoring()` and `autoPassing()`, which are only reachable through
  `followTrajectoryAndIntakeWithSOTM/POTM`, which no shipped auto calls. Dead path, but a trap for
  anyone who enables it. The two call sites also disagree on units: one wraps the value in
  `Units.feetToMeters()`, the other does not.
- **`SwerveSubsystem.targetYaw` is `final Rotation2d.kZero`.** `TRACKING_TARGET` therefore always
  aims at 0°, and its feedforward term is always zero. The mode is not bound to any control.
- **Double unit conversion in `createTestAuto`:** `Units.feetToMeters(DTP_SLOW_VELOCITY_METERS)`,
  where that constant is already in meters — yielding ~0.46 m/s instead of ~1.52 m/s. Confined to
  the TEST auto.
- **`controller.x()` carries two independent bindings** (rotation snap on `whileTrue`, tolerance
  override on `onTrue`). Intentional per the comment, but non-obvious.
- **`RobotState.addPoseObservation()` accepts seven parameters and uses three.** The signature
  anticipates a fuller pose estimator that wasn't built.
- **`Robot.disabledInit()`** has the vision-disable call commented out.

None of these are architectural problems — they are the residue of a six-week build season, and the
logging discipline elsewhere in the codebase is exactly what makes them findable.

---

## 12. Summary

The design in one line: **thin lifecycle → shared state blackboard → IO-abstracted subsystems, each a
two-layer state machine, coordinated by a single hardware-free `SuperStructure`, with every state
transition and API call logged.**

What is most worth learning from it:

1. **`WantedState` / `SystemState` everywhere.** The split lets a subsystem refuse an unsafe request
   (uncalibrated mechanism, finished path) at one well-defined place, and logging both makes intent
   versus behavior visible in replay.
2. **A configuration layer keyed on robot identity.** Every CAN ID, gear ratio, and gain lives in one
   file behind an interface, so practice-bot / comp-bot differences never leak into subsystem code.
3. **Batched, tiered signal refresh.** `StatusSignalRefresher` is a genuinely good answer to CAN
   bandwidth on a robot with ~25 TalonFXs.
4. **Logging as a first-class product.** Not just state — every setter argument, every shot-condition
   predicate independently. It costs a lot of `Logger.recordOutput` lines, and it is what turns
   "it didn't shoot" into a five-minute answer.
5. **Failsafes designed for the drive team, not the code.** `SCORE_KNOWN_TRANSLATION`,
   `SCORE_WITHOUT_OBSERVATION`, `ignoreShootingTolerances`, and the RPM trim slider all assume the
   automation will be wrong at some point during a match and give a human a way through.
