export function SectionHeader({ eyebrow, title, desc }: { eyebrow?: string; title: string; desc: string }) {
  return <div className="section-header">{eyebrow && <span>{eyebrow}</span>}<h2>{title}</h2><p>{desc}</p></div>;
}
