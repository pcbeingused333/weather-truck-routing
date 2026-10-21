import { useEffect, useRef, useState } from "react";
import { geocode } from "../api";
import type { Place } from "../types";

interface Props {
  label: string;
  value: Place | null;
  onChange: (p: Place | null) => void;
  placeholder?: string;
}

/** Text field with debounced place suggestions (Nominatim allows ~1 req/s). */
export default function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const [text, setText] = useState(value?.label ?? "");
  const [options, setOptions] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const skipNext = useRef(false);

  useEffect(() => setText(value?.label ?? ""), [value]);

  useEffect(() => {
    if (skipNext.current) {
      skipNext.current = false;
      return;
    }
    if (text.trim().length < 3 || text === value?.label) {
      setOptions([]);
      return;
    }
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      geocode(text, ctrl.signal)
        .then((res) => {
          setOptions(res);
          setActive(0);
          setOpen(true);
        })
        .catch(() => {});
    }, 450);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [text, value]);

  const choose = (p: Place) => {
    skipNext.current = true;
    onChange(p);
    setText(p.label);
    setOpen(false);
  };

  return (
    <label className="field place">
      <span>{label}</span>
      <input
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          setText(e.target.value);
          if (value) onChange(null);
        }}
        onFocus={() => options.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (!open || !options.length) return;
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, options.length - 1));
          else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          else if (e.key === "Enter") choose(options[active]);
          else return;
          e.preventDefault();
        }}
        aria-autocomplete="list"
      />
      {open && options.length > 0 && (
        <ul className="suggestions" role="listbox">
          {options.map((o, i) => (
            <li key={`${o.lat},${o.lon}`} className={i === active ? "active" : ""} onMouseDown={() => choose(o)}>
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </label>
  );
}
