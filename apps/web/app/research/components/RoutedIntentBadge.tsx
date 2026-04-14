type Props = { intent: string | null };

export function RoutedIntentBadge({ intent }: Props) {
  if (!intent) return null;
  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
      routed to: {intent}
    </span>
  );
}
