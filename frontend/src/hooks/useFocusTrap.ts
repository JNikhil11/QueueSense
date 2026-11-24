import { useEffect, useRef } from 'react';

export interface UseFocusTrapOptions {
  isOpen: boolean;
  onClose: () => void;
  autoFocusSelector?: string;
}

/**
 * Checks whether an element is genuinely focusable, visible, and interactive.
 * Strictly excludes:
 * - Elements with disabled attribute or disabled property
 * - Elements with inert attribute or inside an inert container
 * - Elements with aria-hidden="true"
 * - Elements with explicit negative tabindex (tabindex="-1")
 * - Elements with CSS display: none, visibility: hidden, or visibility: collapse
 * - Elements with zero layout geometry (detached or collapsed)
 */
export function isFocusable(el: HTMLElement | null | undefined): boolean {
  if (!el || typeof el.focus !== 'function') return false;

  // Disabled check
  if ((el as any).disabled || el.hasAttribute('disabled')) return false;

  // Inert and ARIA hidden check
  if (el.hasAttribute('inert') || el.closest('[inert]')) return false;
  if (el.getAttribute('aria-hidden') === 'true') return false;

  // Tabindex check
  const tabIndexAttr = el.getAttribute('tabindex');
  if (tabIndexAttr !== null && parseInt(tabIndexAttr, 10) < 0) return false;

  // CSS computed visibility check
  if (typeof window !== 'undefined') {
    try {
      const style = window.getComputedStyle(el);
      if (
        style.display === 'none' ||
        style.visibility === 'hidden' ||
        style.visibility === 'collapse'
      ) {
        return false;
      }
    } catch {
      // In non-DOM testing environments
    }
  }

  // Geometry check
  const rects = el.getClientRects();
  return (
    rects.length > 0 ||
    el.offsetWidth > 0 ||
    el.offsetHeight > 0 ||
    (typeof el.offsetParent !== 'undefined' && el.offsetParent !== null)
  );
}

/**
 * Queries all currently interactive and visible focusable elements within container.
 * Evaluated on demand to dynamically capture inserted or removed elements.
 */
export function getFocusableElements(container: HTMLElement): HTMLElement[] {
  if (!container) return [];

  const selector = [
    'button:not([disabled])',
    'a[href]',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ');

  const candidates = Array.from(container.querySelectorAll<HTMLElement>(selector));
  return candidates.filter(isFocusable);
}

/**
 * Enterprise WCAG 2.2 AA compliant focus trapping hook with robust lifecycle management.
 * - Stable callback strategy: Parent re-renders or inline onClose identity changes NEVER restart the trap.
 * - True lifecycle restoration: Focus is captured when modal opens and restored ONLY when modal actually closes or unmounts.
 * - Dynamic element resilience: Focus sequence dynamically adjusts to added/removed children.
 * - Pointer & Keyboard containment: Prevents keyboard or pointer focus from escaping the active modal.
 * - Zero-element safety: Safely focuses modal container if no interactive children exist.
 */
export function useFocusTrap<T extends HTMLElement = HTMLDivElement>({
  isOpen,
  onClose,
  autoFocusSelector,
}: UseFocusTrapOptions) {
  const containerRef = useRef<T>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  // Stable callback and selector references to decouple from effect dependencies
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const autoFocusSelectorRef = useRef(autoFocusSelector);
  autoFocusSelectorRef.current = autoFocusSelector;

  // Track previous isOpen state to detect actual transitions
  const wasOpenRef = useRef<boolean>(false);

  // LIFECYCLE EFFECT: Captures trigger element on open; restores focus ONLY on close/unmount.
  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      // Transition: closed -> open
      wasOpenRef.current = true;
      if (typeof document !== 'undefined') {
        const active = document.activeElement as HTMLElement | null;
        // Only capture if active element is outside our modal container
        if (active && (!containerRef.current || !containerRef.current.contains(active))) {
          previousActiveElementRef.current = active;
        }
      }
    } else if (!isOpen && wasOpenRef.current) {
      // Transition: open -> closed
      wasOpenRef.current = false;
      safelyRestoreFocus();
    }

    return () => {
      // Unmount while modal was open
      if (wasOpenRef.current) {
        wasOpenRef.current = false;
        safelyRestoreFocus();
      }
    };
  }, [isOpen]);

  function safelyRestoreFocus() {
    const el = previousActiveElementRef.current;
    if (el && typeof el.focus === 'function') {
      try {
        if (typeof document !== 'undefined' && document.contains(el)) {
          if (!((el as any).disabled || el.hasAttribute('disabled'))) {
            el.focus();
          }
        }
      } catch {
        // Fallback safely if focus cannot be set
      }
    }
    previousActiveElementRef.current = null;
  }

  // TRAP INTERACTION EFFECT: Sets up event listeners and manages auto-focus.
  // Note: Runs ONLY when isOpen transitions. Parent re-renders do NOT re-run this effect!
  useEffect(() => {
    if (!isOpen) return;

    const container = containerRef.current;
    if (!container) return;

    // Ensure container can receive focus as fallback for zero focusable elements
    if (!container.hasAttribute('tabindex')) {
      container.setAttribute('tabindex', '-1');
    }

    // Auto-focus initial element on next tick
    const autoFocusTimer = setTimeout(() => {
      if (!container || (typeof document !== 'undefined' && !document.contains(container))) return;

      // If user or browser already placed focus inside container, preserve it
      if (
        typeof document !== 'undefined' &&
        document.activeElement &&
        container.contains(document.activeElement) &&
        document.activeElement !== container
      ) {
        return;
      }

      const focusable = getFocusableElements(container);
      if (autoFocusSelectorRef.current) {
        const target = container.querySelector<HTMLElement>(autoFocusSelectorRef.current);
        if (target && isFocusable(target)) {
          target.focus();
          return;
        }
      }

      if (focusable.length > 0) {
        focusable[0].focus();
      } else {
        container.focus();
      }
    }, 40);

    // Keyboard Tab / Shift+Tab Trapping and Escape Handling
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        onCloseRef.current();
        return;
      }

      if (e.key === 'Tab') {
        const focusable = getFocusableElements(container);

        if (focusable.length === 0) {
          // Zero focusable elements: keep focus on container
          e.preventDefault();
          container.focus();
          return;
        }

        const firstElement = focusable[0];
        const lastElement = focusable[focusable.length - 1];
        const activeEl = document.activeElement;

        if (e.shiftKey) {
          // Shift + Tab: if on first element or outside modal, cycle to last element
          if (activeEl === firstElement || !container.contains(activeEl)) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          // Tab: if on last element or outside modal, cycle to first element
          if (activeEl === lastElement || !container.contains(activeEl)) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    // Pointer & External Focus Containment
    // If pointer interaction or external script moves focus outside active modal, bring it back
    const handleFocusIn = (e: FocusEvent) => {
      if (!container || (typeof document !== 'undefined' && !document.contains(container))) return;
      const target = e.target as HTMLElement | null;

      if (target && !container.contains(target)) {
        e.preventDefault();
        e.stopImmediatePropagation();
        const focusable = getFocusableElements(container);
        if (focusable.length > 0) {
          focusable[0].focus();
        } else {
          container.focus();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown, true);
    if (typeof document !== 'undefined') {
      document.addEventListener('focusin', handleFocusIn, true);
    }

    return () => {
      clearTimeout(autoFocusTimer);
      window.removeEventListener('keydown', handleKeyDown, true);
      if (typeof document !== 'undefined') {
        document.removeEventListener('focusin', handleFocusIn, true);
      }
      // CRITICAL: NO focus restoration here! Routine effect cleanup must NEVER steal focus.
    };
  }, [isOpen]);

  return containerRef;
}
