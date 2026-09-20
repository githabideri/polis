using System;
using Vintagestory.API.Common;
using Vintagestory.API.Common.Entities;

namespace PolisBuilderNpc.Helpers;

/// <summary>
/// Helper class for managing entity animations, particularly looping animations.
///
/// In Vintage Story, most animations (like "hit", "interact") are one-shot - they play once
/// and stop. To create a looping effect, we must periodically re-trigger the animation.
/// Some animations (like "walk", "idle") are inherently looping in the shape definition,
/// but for one-shot animations used in continuous actions (mining, smithing, etc.),
/// we need explicit re-triggering.
///
/// This helper provides:
/// - LoopingAnimationState: tracks a looping animation and re-triggers it when it ends
/// - StartLoopingAnimation: begins a looping animation cycle
/// - UpdateLoopingAnimation: call in OnTick to check and re-trigger as needed
/// - StopLoopingAnimation: cleanly stops the animation
/// </summary>
internal static class PolisAnimationHelpers
{
    /// <summary>
    /// Tracks state for a looping animation that needs periodic re-triggering.
    /// </summary>
    internal class LoopingAnimationState
    {
        public string AnimCode { get; set; }
        public float AnimSpeed { get; set; }
        public bool IsActive { get; set; }
        public float TimeSinceLastStart { get; set; }
        public float MinRetriggerInterval { get; set; }

        public LoopingAnimationState(string animCode, float animSpeed = 1.0f, float minRetriggerInterval = 0.3f)
        {
            AnimCode = animCode;
            AnimSpeed = animSpeed;
            IsActive = false;
            TimeSinceLastStart = 0f;
            MinRetriggerInterval = minRetriggerInterval;
        }
    }

    /// <summary>
    /// Starts a looping animation. Call UpdateLoopingAnimation() in OnTick to maintain the loop.
    /// </summary>
    /// <param name="entity">The entity to animate</param>
    /// <param name="state">The looping animation state to initialize and track</param>
    /// <param name="debugLog">Optional debug logging callback</param>
    /// <returns>True if animation started successfully</returns>
    internal static bool StartLoopingAnimation(EntityAgent entity, LoopingAnimationState state, Action<string> debugLog = null)
    {
        if (entity == null || state == null || string.IsNullOrEmpty(state.AnimCode))
        {
            return false;
        }

        var animMeta = new AnimationMetaData
        {
            Code = state.AnimCode,
            Animation = state.AnimCode,
            AnimationSpeed = state.AnimSpeed,
            BlendMode = EnumAnimationBlendMode.Average
        };
        animMeta.EaseInSpeed = 1f;
        animMeta.EaseOutSpeed = 1f;

        bool started = entity.AnimManager.StartAnimation(animMeta.Init());
        if (started)
        {
            state.IsActive = true;
            state.TimeSinceLastStart = 0f;
            debugLog?.Invoke($"[anim] started looping animation '{state.AnimCode}' speed={state.AnimSpeed:F2}");
        }
        else
        {
            debugLog?.Invoke($"[anim] failed to start animation '{state.AnimCode}'");
        }

        return started;
    }

    /// <summary>
    /// Updates a looping animation, re-triggering it at fixed intervals.
    /// Call this in your action's OnTick method.
    ///
    /// Note: We use fixed-interval re-triggering because VS's IsAnimationActive()
    /// returns true even after an animation visually completes (it stays "active"
    /// until explicitly stopped). So we re-trigger based on time elapsed instead.
    /// </summary>
    /// <param name="entity">The entity being animated</param>
    /// <param name="state">The looping animation state</param>
    /// <param name="dt">Delta time from OnTick</param>
    /// <param name="debugLog">Optional debug logging callback</param>
    internal static void UpdateLoopingAnimation(EntityAgent entity, LoopingAnimationState state, float dt, Action<string> debugLog = null)
    {
        if (entity == null || state == null || !state.IsActive)
        {
            return;
        }

        state.TimeSinceLastStart += dt;

        // Re-trigger animation at fixed intervals based on estimated duration
        // The "hit" animation is roughly 0.5-0.6s at speed 1.0
        // We re-trigger slightly before it would end to ensure continuous motion
        float retriggerInterval = state.MinRetriggerInterval / Math.Max(0.1f, state.AnimSpeed);

        if (state.TimeSinceLastStart >= retriggerInterval)
        {
            // Re-trigger the animation
            var animMeta = new AnimationMetaData
            {
                Code = state.AnimCode,
                Animation = state.AnimCode,
                AnimationSpeed = state.AnimSpeed,
                BlendMode = EnumAnimationBlendMode.Average
            };
            animMeta.EaseInSpeed = 1f;
            animMeta.EaseOutSpeed = 1f;

            entity.AnimManager.StartAnimation(animMeta.Init());
            state.TimeSinceLastStart = 0f;

            debugLog?.Invoke($"[anim] re-triggered looping animation '{state.AnimCode}'");
        }
    }

    /// <summary>
    /// Stops a looping animation cleanly.
    /// </summary>
    /// <param name="entity">The entity being animated</param>
    /// <param name="state">The looping animation state</param>
    /// <param name="debugLog">Optional debug logging callback</param>
    internal static void StopLoopingAnimation(EntityAgent entity, LoopingAnimationState state, Action<string> debugLog = null)
    {
        if (entity == null || state == null)
        {
            return;
        }

        if (state.IsActive)
        {
            entity.AnimManager.StopAnimation(state.AnimCode);
            state.IsActive = false;
            debugLog?.Invoke($"[anim] stopped looping animation '{state.AnimCode}'");
        }
    }

    /// <summary>
    /// Plays a one-shot animation (non-looping).
    /// </summary>
    /// <param name="entity">The entity to animate</param>
    /// <param name="animCode">The animation code</param>
    /// <param name="speed">Animation speed multiplier</param>
    /// <param name="debugLog">Optional debug logging callback</param>
    /// <returns>True if animation started successfully</returns>
    internal static bool PlayOneShotAnimation(EntityAgent entity, string animCode, float speed = 1.0f, Action<string> debugLog = null)
    {
        if (entity == null || string.IsNullOrEmpty(animCode))
        {
            return false;
        }

        var animMeta = new AnimationMetaData
        {
            Code = animCode,
            Animation = animCode,
            AnimationSpeed = speed,
            BlendMode = EnumAnimationBlendMode.Average
        };
        animMeta.EaseInSpeed = 1f;
        animMeta.EaseOutSpeed = 1f;

        bool started = entity.AnimManager.StartAnimation(animMeta.Init());
        if (started)
        {
            debugLog?.Invoke($"[anim] played one-shot animation '{animCode}' speed={speed:F2}");
        }

        return started;
    }

    /// <summary>
    /// Stops a specific animation by code.
    /// </summary>
    /// <param name="entity">The entity</param>
    /// <param name="animCode">The animation code to stop</param>
    internal static void StopAnimation(EntityAgent entity, string animCode)
    {
        if (entity == null || string.IsNullOrEmpty(animCode))
        {
            return;
        }

        entity.AnimManager.StopAnimation(animCode);
    }
}
