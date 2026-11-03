import { useCallback, useEffect, useRef, useState } from 'react';

// Block A5: safe polling. One request at a time, fixed interval while healthy,
// exponential backoff on errors (capped), paused while the browser tab is hidden.
const usePolling = (fetcher, { interval = 15000, maxBackoff = 120000 } = {}) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [lastSuccess, setLastSuccess] = useState(null);
  const [nextDelay, setNextDelay] = useState(interval);
  const timer = useRef(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const failures = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    let delay = interval;
    try {
      const result = await fetcherRef.current();
      if (!mounted.current) return;            // unmounted mid-request: no state update, no reschedule
      setData(result);
      setError('');
      setLastSuccess(new Date());
      failures.current = 0;
    } catch (err) {
      if (!mounted.current) return;
      failures.current += 1;
      delay = Math.min(maxBackoff, interval * 2 ** failures.current);
      setError(err.message || 'Request failed');
    } finally {
      inFlight.current = false;
      if (!mounted.current) return;            // eslint-disable-line no-unsafe-finally
      setNextDelay(delay);
      clearTimeout(timer.current);
      if (!document.hidden) timer.current = setTimeout(run, delay);
    }
  }, [interval, maxBackoff]);

  useEffect(() => {
    mounted.current = true;
    run();
    const onVisibility = () => {
      clearTimeout(timer.current);
      if (!document.hidden) run();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      mounted.current = false;
      clearTimeout(timer.current);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [run]);

  return { data, error, lastSuccess, nextDelay, refresh: run };
};

export default usePolling;
