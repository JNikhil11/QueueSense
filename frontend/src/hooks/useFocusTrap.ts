import { useEffect, useRef } from 'react';

interface UseFocusTrapOptions {
  isOpen: boolean;
  onClose: () => void;
  autoFocusSelector?: string;
}

/**
 * Custom React hook for WCAG 2.2 AA compliant focus trapping within modals.
 * - Saves the trigger element on open and restores focus to it on close/unmount.
 * - Auto-focuses the first interactive element (or specified selector) inside the modal on open.
 * - Traps Tab and Shift+Tab keyboard navigation strictly within modal focusable elements.
 * - Handles Escape key to dismiss the modal.
 */
export function useFocusTrap<T extends HTMLElement = HTMLDivElement>({
  isOpen,
  onClose,
  autoFocusSelector,
}: UseFocusTrapOptions) {
  const containerRef = useRef<T>(null);
  const previousActiveElementRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Capture the trigger element that had focus before the modal opened
    if (typeof document !== 'undefined') {
      previousActiveElementRef.current = document.activeElement as HTMLElement | null;
    }

    const container = containerRef.current;
    if (!container) return;

    const getFocusableElements = (): HTMLElement[] => {
      const selector =
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
      return Array.from(container.querySelectorAll<HTMLElement>(selector)).filter((el) => {
        // Element is visible and interactive
        return (
          el.offsetParent !== null ||
          el.getClientRects().length > 0 ||
          window.getComputedStyle(el).display !== 'none'
        );
      });
    };

    // Auto-focus initial element on next microtask/frame
    const timer = setTimeout(() => {
      const focusable = getFocusableElements();
      if (focusable.length === 0) return;

      if (autoFocusSelector) {
        const target = container.querySelector<HTMLElement>(autoFocusSelector);
        if (target && focusable.includes(target)) {
          target.focus();
          return;
        }
      }
      focusable[0].focus();
    }, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === 'Tab') {
        const focusable = getFocusableElements();
        if (focusable.length === 0) {
          e.preventDefault();
          return;
        }

        const firstElement = focusable[0];
        const lastElement = focusable[focusable.length - 1];

        if (e.shiftKey) {
          // Shift + Tab: if on first element or outside, cycle to last element
          if (
            document.activeElement === firstElement ||
            !container.contains(document.activeElement)
          ) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          // Tab: if on last element or outside, cycle to first element
          if (
            document.activeElement === lastElement ||
            !container.contains(document.activeElement)
          ) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
      // Restore focus to the element that triggered the modal
      if (
        previousActiveElementRef.current &&
        typeof previousActiveElementRef.current.focus === 'function' &&
        document.contains(previousActiveElementRef.current)
      ) {
        previousActiveElementRef.current.focus();
      }
    };
  }, [isOpen, onClose, autoFocusSelector]);

  return containerRef;
}

