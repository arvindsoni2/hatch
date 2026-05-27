interface Props { text: string; keywords: string[]; }

export function SafeHighlight({ text, keywords }: Props) {
  if (!keywords.length) return <span>{text}</span>;
  const regex = new RegExp(
    `(${keywords.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
    'gi',
  );
  const parts = text.split(regex);
  return (
    <span>
      {parts.map((part, i) =>
        keywords.some(k => k.toLowerCase() === part.toLowerCase())
          ? <mark key={i} className="bg-yellow-100 dark:bg-yellow-900/30 px-0.5 rounded">{part}</mark>
          : <span key={i}>{part}</span>
      )}
    </span>
  );
}
