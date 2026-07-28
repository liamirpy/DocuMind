import Link from "next/link";

export function Brand() {
  return (
    <Link className="brand" href="/" aria-label="DocuMind home">
      <span className="brand-mark" aria-hidden="true">
        D
      </span>
      <span>DocuMind</span>
    </Link>
  );
}
