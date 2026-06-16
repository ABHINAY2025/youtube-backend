// The animated devX blob — bobs and blinks; CSS drives the motion.
export default function Mascot({ className = "blob-svg" }) {
  return (
    <svg viewBox="0 0 120 120" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="devxBody" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#8fd3f4" />
          <stop offset="1" stopColor="#5DB7E8" />
        </linearGradient>
      </defs>
      <ellipse className="shadow" cx="60" cy="104" rx="30" ry="6" />
      <path
        className="body"
        fill="url(#devxBody)"
        stroke="#2f6ea5"
        strokeWidth="3"
        d="M60 18c20 0 34 16 34 38 0 26-16 42-34 42S26 82 26 56C26 34 40 18 60 18Z"
      />
      <circle className="eye" cx="50" cy="54" r="4.2" />
      <circle className="eye" cx="72" cy="54" r="4.2" />
      <path
        className="smile"
        d="M50 66 Q61 76 72 66"
        fill="none"
        stroke="#234"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <ellipse className="shine" cx="52" cy="40" rx="6" ry="9" fill="#fff" opacity="0.75" />
    </svg>
  );
}
