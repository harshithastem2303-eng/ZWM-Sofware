import React, { useState, useEffect, useRef } from 'react';
import useInView from '../hooks/useInView';

/**
 * Animated CountUp component that counts up from 0 to target number when scrolled into view.
 */
const CountUp = ({
  end = 0,
  duration = 1000,
  prefix = '',
  suffix = '',
  decimals = 0,
  className = '',
  style = {}
}) => {
  const [ref, isInView] = useInView({ threshold: 0.1 }, true);
  const [displayValue, setDisplayValue] = useState(0);
  const rafRef = useRef(null);
  const startRef = useRef(null);

  const targetNum = typeof end === 'number' ? end : parseFloat(end) || 0;

  useEffect(() => {
    if (!isInView) {
      setDisplayValue(0);
      return;
    }

    if (targetNum === 0) {
      setDisplayValue(0);
      return;
    }

    startRef.current = performance.now();

    const animate = (now) => {
      const elapsed = now - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      // Smooth ease-out cubic function: 1 - (1 - t)^3
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = eased * targetNum;

      setDisplayValue(current);

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        setDisplayValue(targetNum);
      }
    };

    rafRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isInView, targetNum, duration]);

  const formattedValue = decimals > 0
    ? displayValue.toFixed(decimals)
    : Math.round(displayValue).toLocaleString();

  return (
    <span ref={ref} className={className} style={{ display: 'inline-block', ...style }}>
      {prefix}{formattedValue}{suffix}
    </span>
  );
};

export default CountUp;
