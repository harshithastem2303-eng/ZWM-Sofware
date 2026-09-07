import { useState, useEffect, useRef } from 'react';

/**
 * Custom React hook that monitors an element's visibility in the viewport.
 * Returns [ref, isInView].
 *
 * @param {Object} options IntersectionObserver options (threshold, rootMargin, etc.)
 * @param {boolean} triggerOnce If true, stays true after entering viewport once.
 */
export const useInView = (options = { threshold: 0.15 }, triggerOnce = true) => {
  const ref = useRef(null);
  const [isInView, setIsInView] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (typeof IntersectionObserver === 'undefined') {
      setIsInView(true);
      return;
    }

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setIsInView(true);
        if (triggerOnce) {
          observer.unobserve(node);
        }
      } else if (!triggerOnce) {
        setIsInView(false);
      }
    }, options);

    observer.observe(node);

    return () => {
      if (node) observer.unobserve(node);
    };
  }, [options.threshold, options.rootMargin, triggerOnce]);

  return [ref, isInView];
};

export default useInView;
