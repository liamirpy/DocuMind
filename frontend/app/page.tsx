"use client";

import Link from "next/link";
import { Brand } from "@/components/brand";
import { LoadingScreen } from "@/components/loading-screen";
import { useAuth } from "@/lib/auth-context";

export default function HomePage() {
  const { status } = useAuth();

  if (status === "loading") {
    return <LoadingScreen />;
  }

  return (
    <main className="home-page">
      <nav className="home-nav">
        <Brand />
        <div className="nav-actions">
          {status === "authenticated" ? (
            <Link className="button button-primary button-small" href="/dashboard">
              Open workspace
            </Link>
          ) : (
            <>
              <Link className="button button-ghost button-small" href="/login">
                Sign in
              </Link>
              <Link className="button button-primary button-small" href="/register">
                Create account
              </Link>
            </>
          )}
        </div>
      </nav>

      <section className="hero">
        <p className="eyebrow">One conversation. Every document.</p>
        <h1>Your PDFs become a workspace you can talk to.</h1>
        <p className="hero-copy">
          Build folders, upload files, and ask questions across one document or
          your entire library. Your private workspace stays connected to the
          existing DocuMind API.
        </p>
        <div className="hero-actions">
          <Link
            className="button button-primary"
            href={status === "authenticated" ? "/dashboard" : "/register"}
          >
            {status === "authenticated" ? "Continue to dashboard" : "Start Now"}
          </Link>
          {status === "unauthenticated" && (
            <Link className="button button-secondary" href="/login">
              I already have an account
            </Link>
          )}
        </div>
      <p className="developer-credit">
          Developed by <strong style={{color:"green"}}>Amir Mousavi</strong>{" "}
        </p>

      </section>
    </main>
  );
}
