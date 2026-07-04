import { useState, useEffect } from "react";

export function useTypewriter(text, speed = 18) {
  const [displayed, setDisplayed] = useState("");
  useEffect(() => {
    setDisplayed("");
    if (!text) return;
    let i = 0;
    const iv = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(iv);
    }, speed);
    return () => clearInterval(iv);
  }, [text]);
  return displayed;
}

export function useBlink(interval = 530) {
  const [on, setOn] = useState(true);
  useEffect(() => {
    const iv = setInterval(() => setOn(p => !p), interval);
    return () => clearInterval(iv);
  }, [interval]);
  return on;
}
