import Link from 'next/link';
import {TraceMark} from './trace/trace-mark';

export function BrandLogo({size = 30, onDark = false}: {size?: number; onDark?: boolean}) {
  return (
    <Link className={onDark ? 'brand brand-on-dark' : 'brand'} href="/">
      <span className="brand-logo"><TraceMark concept="converge" size={size} /></span>
      <span className="brand-text">DeepTrace</span>
    </Link>
  );
}
