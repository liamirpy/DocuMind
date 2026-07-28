"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AuthShell } from "@/components/auth-shell";
import { LoadingScreen } from "@/components/loading-screen";
import { ApiError } from "@/lib/auth-api";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { login, status } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/dashboard");
    }
  }, [router, status]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      await login({ email: email.trim().toLowerCase(), password });
      router.replace("/dashboard");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to sign in. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (status === "loading" || status === "authenticated") {
    return <LoadingScreen />;
  }

  return (
    <AuthShell
      eyebrow="Welcome back"
      title="Sign in to your workspace"
      description="Use the email and password connected to your DocuMind account."
      footer={
        <p>
          New to DocuMind? <Link href="/register">Create an account</Link>
        </p>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        {error && (
          <div className="form-alert" role="alert">
            {error}
          </div>
        )}

        <label className="field">
          <span>Email address</span>
          <input
            autoComplete="email"
            inputMode="email"
            name="email"
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            required
            type="email"
            value={email}
          />
        </label>

        <label className="field">
          <span>Password</span>
          <input
            autoComplete="current-password"
            minLength={8}
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            placeholder="At least 8 characters"
            required
            type="password"
            value={password}
          />
        </label>

        <button className="button button-primary button-full" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthShell>
  );
}
