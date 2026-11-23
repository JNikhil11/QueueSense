import React, { useEffect, useRef, useState } from 'react';

export interface CinematicVideoBackgroundProps {
  isOverlayActive: boolean;
  videoSrc?: string;
  posterSrc?: string;
}

export const CinematicVideoBackground: React.FC<CinematicVideoBackgroundProps> = ({
  isOverlayActive,
  videoSrc = '/videos/jellyfish.mp4',
  posterSrc = '/videos/jellyfish-poster.jpg',
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });

  // Track prefers-reduced-motion OS accessibility preference
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handleChange = (e: MediaQueryListEvent) => {
      setPrefersReducedMotion(e.matches);
    };

    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    } else {
      mediaQuery.addListener(handleChange);
      return () => mediaQuery.removeListener(handleChange);
    }
  }, []);

  // Explicitly ensure muted is active to satisfy strict browser autoplay policies
  useEffect(() => {
    const video = videoRef.current;
    if (video) {
      video.muted = true;
      video.defaultMuted = true;
    }
  }, []);

  // Modal / Overlay Synchronization & Playback Controller
  // Non-negotiable requirement:
  // - When ANY interactive overlay opens: immediately pause the video and hide the video layer (display: none),
  //   revealing the solid #070A08 background. Zero fade animation or transition delay.
  // - When all overlays close: reveal video layer instantly and resume playback from exact previous currentTime
  //   without reloading or restarting from beginning.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    if (isOverlayActive || prefersReducedMotion) {
      // Immediately pause playback
      video.pause();
    } else {
      // Resume playback without resetting currentTime or reloading
      const playPromise = video.play();
      if (playPromise !== undefined) {
        playPromise.catch((err) => {
          // AbortError is normal when quickly paused/closed; ignore
          if (err.name !== 'AbortError' && err.name !== 'NotAllowedError') {
            console.debug('CinematicVideoBackground playback notice:', err);
          }
        });
      }
    }
  }, [isOverlayActive, prefersReducedMotion]);

  // Clean shutdown on unmount
  useEffect(() => {
    const video = videoRef.current;
    return () => {
      if (video) {
        video.pause();
      }
    };
  }, []);

  return (
    <div
      data-testid="cinematic-video-layer"
      aria-hidden="true"
      className="fixed inset-0 pointer-events-none z-0 overflow-hidden"
      style={{
        // Zero-latency instant toggle between visible video and solid #070A08 background
        display: isOverlayActive ? 'none' : 'block',
      }}
    >
      {/* Video Element: stays mounted across modal open/close to preserve currentTime */}
      <video
        ref={videoRef}
        src={videoSrc}
        poster={posterSrc}
        autoPlay={!prefersReducedMotion && !isOverlayActive}
        loop
        muted
        playsInline
        preload="auto"
        className="w-full h-full object-cover object-[center_35%]"
        style={{
          display: prefersReducedMotion ? 'none' : 'block',
        }}
      />

      {/* Static Poster Fallback for Reduced Motion */}
      {prefersReducedMotion && (
        <img
          src={posterSrc}
          alt=""
          className="w-full h-full object-cover object-[center_35%]"
        />
      )}

      {/* Atmospheric Contrast Scrim Layer
          Carefully tuned dark scrim ensures WCAG AA text contrast while preserving
          the rich bioluminescent motion of the jellyfish in negative space. */}
      <div className="absolute inset-0 bg-[#070A08]/40 pointer-events-none" />
      <div className="absolute inset-0 bg-gradient-to-b from-[#070A08]/60 via-transparent to-[#070A08]/80 pointer-events-none" />
    </div>
  );
};

