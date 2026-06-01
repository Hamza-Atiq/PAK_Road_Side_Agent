// Apple / Google / Facebook sign-in stubs. Backend OAuth lands in Week 5;
// for now we show the buttons and route clicks to phone signup with an info toast.

import { useState } from "react";

interface Props {
  role: "customer" | "provider";
}

export function SocialSignIn({ role }: Props) {
  const [comingSoon, setComingSoon] = useState<string | null>(null);

  const onClick = (provider: string) => {
    setComingSoon(provider);
    setTimeout(() => setComingSoon(null), 2500);
  };

  const providers = [
    { id: "apple", label: "Continue with Apple", icon: "" },
    { id: "google", label: "Continue with Google", icon: "G" },
    { id: "facebook", label: "Continue with Facebook", icon: "f" },
  ];

  return (
    <div className="space-y-2">
      {providers.map((p) => (
        <button
          key={p.id}
          type="button"
          onClick={() => onClick(p.id)}
          className="flex w-full items-center justify-center gap-3 rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-800 transition hover:bg-slate-50 active:scale-[0.99]"
        >
          <span aria-hidden className="text-lg font-black">
            {p.icon}
          </span>
          {p.label}
        </button>
      ))}
      <p className="text-center text-xs text-slate-500">
        {comingSoon
          ? `${comingSoon} sign-in launches with mobile (Week 5). Use phone for now.`
          : `New here? Use phone signup below as ${role}.`}
      </p>
    </div>
  );
}
