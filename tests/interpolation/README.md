# Interpolation regression

Run after pointing `VINTAGE_STORY` at a Vintage Story 1.22.7 installation:

```sh
python3 tests/interpolation/run.py --game "$VINTAGE_STORY"
```

Requires the .NET 10 SDK and the game's bundled assemblies. The runner compiles
the production Harmony patch into a temporary console test, invokes the actual
engine interpolation method, then removes its temporary build directory. It
does not start the game or create a graphics context.

The original engine must reproduce a non-finite position. The patched method
must remain finite across stationary and moving inputs at fast and slow frame
rates, mixed stalls, and zero dt. The test also checks that speed arithmetic for
ordinary frame times is unchanged.

`Program.cs.txt` is deliberately not a `.cs` file: the mod's default source
glob must not compile the standalone test program into the mod.
