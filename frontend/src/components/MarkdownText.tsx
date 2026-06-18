function renderInlineBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <span key={index}>{formatMathDisplayText(part)}</span>;
  });
}

function formatMathDisplayText(text: string) {
  return text
    .replace(/(?<=\d)\s*([+\-])\s*(?=\d)/g, ' $1 ')
    .replace(/(?<=\d)\s*\*(?=\d)/g, ' × ')
    .replace(/\*/g, '×')
    .replace(/->/g, '→');
}

export function MarkdownText({ text }: { text: string }) {
  return <p>
    {text.split('\n').map((line, index, lines) => <span key={index}>
      {renderInlineBold(line)}
      {index < lines.length - 1 && <br />}
    </span>)}
  </p>;
}
