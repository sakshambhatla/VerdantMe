import { useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function LoginPage() {
  const { signIn, signUp } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSignUp, setIsSignUp] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [signUpSuccess, setSignUpSuccess] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const result = isSignUp
      ? await signUp(email, password)
      : await signIn(email, password);

    setLoading(false);

    if (result) {
      setError(result);
    } else if (isSignUp) {
      setSignUpSuccess(true);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center relative overflow-hidden"
      style={{ background: "var(--app-gradient)" }}
    >
      {/* Aurora orbs */}
      <div className="pointer-events-none" aria-hidden="true">
        <div className="glass-orb glass-orb-1" />
        <div className="glass-orb glass-orb-2" />
        <div className="glass-orb glass-orb-3" />
      </div>

      <Card className="w-full max-w-md relative z-10 glass-card">
        <CardHeader className="text-center">
          <h1
            className="text-4xl font-black tracking-tight text-white mb-1"
            style={{ fontFamily: "var(--font-display)" }}
          >
            VerdantMe
          </h1>
          <CardTitle className="text-lg font-normal" style={{ color: "rgba(255,255,255,0.6)" }}>
            {isSignUp ? "Create your account" : "Sign in to your account"}
          </CardTitle>
        </CardHeader>

        <CardContent>
          {signUpSuccess ? (
            <div className="text-center py-4">
              <p className="text-green-400 mb-2">Account created!</p>
              <p style={{ color: "rgba(255,255,255,0.6)" }}>
                Check your email for a confirmation link, then sign in.
              </p>
              <Button
                variant="ghost"
                className="mt-4"
                onClick={() => {
                  setIsSignUp(false);
                  setSignUpSuccess(false);
                }}
              >
                Back to sign in
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                />
              </div>

              {error && (
                <p className="text-red-400 text-sm">{error}</p>
              )}

              <Button type="submit" className="w-full" disabled={loading}>
                {loading && (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent mr-2" />
                )}
                {isSignUp ? "Create account" : "Sign in"}
              </Button>

              <p className="text-center text-sm" style={{ color: "rgba(255,255,255,0.5)" }}>
                {isSignUp ? "Already have an account?" : "Don't have an account?"}{" "}
                <button
                  type="button"
                  className="underline text-white"
                  onClick={() => {
                    setIsSignUp(!isSignUp);
                    setError(null);
                  }}
                >
                  {isSignUp ? "Sign in" : "Sign up"}
                </button>
              </p>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
