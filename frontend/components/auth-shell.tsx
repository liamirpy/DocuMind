import type { ReactNode } from "react";
import { Brand } from "@/components/brand";

export function AuthShell({
  eyebrow,
  title,
  description,
  children,
  footer,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="Product introduction">
        <Brand />
        <div className="story-copy">
          <p className="eyebrow">Your private document workspace</p>
          <h1>Ask better questions of every PDF you own.</h1>
          <p>
            Organise documents into focused libraries, then chat with one file
            or an entire folder from a single workspace.
          </p>
        </div>
        {/* <div className="story-card" aria-hidden="true">
          <div className="story-card-top">
            <span className="story-dot" />
            Research / Q3 reports
          </div>
          <div className="story-message story-message-user">
            Compare the risks mentioned across these files.
          </div>
          <div className="story-message story-message-ai">
            I found three recurring risks: supplier concentration, regulatory
            delays, and foreign-exchange exposure.
          </div>
        </div> */}
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="mobile-brand">
            <Brand />
          </div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p className="auth-description">{description}</p>
          {children}
          <div className="auth-footer">{footer}</div>
        </div>
      </section>
    </main>
  );
}
