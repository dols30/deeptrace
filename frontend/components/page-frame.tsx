export function PageFrame({children}: {children: React.ReactNode}) {
  return <div className="page-frame">
    <div className="page-frame-body">{children}</div>
  </div>;
}
