export function rupees(paise: number): string {
  const value = paise / 100;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function rupeesPlain(amount: number): string {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(amount);
}

export function shortId(id: string, keep = 10): string {
  return id.length <= keep ? id : `${id.slice(0, keep)}\u2026`;
}

export function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 90) return `${Math.round(seconds)}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 129600) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function factorLabel(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace("72h", "72h")
    .replace("device identity ratio", "identities / device")
    .replace("cross merchant fanout", "cross-merchant fan-out")
    .replace("taint propagation", "taint proximity")
    .replace("velocity 72h", "72h merchant velocity")
    .replace("burn rotate", "burn-and-rotate")
    .replace("amount pattern", "amount-band fit")
    .replace("new identity burst", "new-identity burst");
}
