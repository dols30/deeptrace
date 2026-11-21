import type {Metadata} from 'next';
import {notFound} from 'next/navigation';
import {DesignLab} from '../../components/design-lab/design-lab';

export const metadata: Metadata = {
  title: 'Design lab — DeepTrace',
  robots: {index: false, follow: false},
};

export default function DesignLabPage() {
  if (process.env.NODE_ENV === 'production' && process.env.NEXT_PUBLIC_DESIGN_LAB !== '1') notFound();
  return <DesignLab />;
}
