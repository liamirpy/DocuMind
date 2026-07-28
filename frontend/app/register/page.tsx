"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { AuthShell } from "@/components/auth-shell";
import { LoadingScreen } from "@/components/loading-screen";
import { ApiError } from "@/lib/auth-api";
import { useAuth } from "@/lib/auth-context";

export default function RegisterPage() {
  const router = useRouter();
  const { register, status } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);

    try {
      await register({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim().toLowerCase(),
        password,
      });
      router.replace("/dashboard");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to create your account. Please try again.",
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
      eyebrow="Create your account"
      title="Start your document workspace"
      description="Create an account now. Folder and PDF tools will be added in the next milestone."
      footer={
        <p>
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        {error && (
          <div className="form-alert" role="alert">
            {error}
          </div>
        )}

        <div className="field-row">
          <label className="field">
            <span>First name</span>
            <input
              autoComplete="given-name"
              name="first_name"
              onChange={(event) => setFirstName(event.target.value)}
              placeholder="Jane"
              required
              value={firstName}
            />
          </label>

          <label className="field">
            <span>Last name</span>
            <input
              autoComplete="family-name"
              name="last_name"
              onChange={(event) => setLastName(event.target.value)}
              placeholder="Doe"
              required
              value={lastName}
            />
          </label>
        </div>

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
            autoComplete="new-password"
            minLength={8}
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            placeholder="At least 8 characters"
            required
            type="password"
            value={password}
          />
        </label>

        <label className="field">
          <span>Confirm password</span>
          <input
            autoComplete="new-password"
            minLength={8}
            name="confirm_password"
            onChange={(event) => setConfirmPassword(event.target.value)}
            placeholder="Repeat your password"
            required
            type="password"
            value={confirmPassword}
          />
        </label>

        <button className="button button-primary button-full" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
    </AuthShell>
  );
}
