import type {Metadata} from 'next';
import Link from 'next/link';
import Image from 'next/image';
import {SiteHeader} from '../../components/header';
import {SiteFooter} from '../../components/footer';

export const metadata: Metadata = {
  title: 'About | DeepTrace',
  description: 'Meet Silicon Peaks, the University of Southern Mississippi team building DeepTrace.',
};

const team = [
  {photo: '/team/dol-raj-bashyal.png', name: 'Dol Raj Bashyal', role: 'Application & Cloud', focus: 'Full-stack systems, cloud, and security.', github: 'https://github.com/dols30'},
  {photo: '/team/krish-karki.png', name: 'Krish Karki', role: 'Audio & Evaluation', focus: 'Audio models, data, and evaluation.', github: 'https://github.com/Kirishdai'},
  {photo: '/team/tarbi-pyakurel.png', name: 'Tarbi Pyakurel', role: 'Video & ML', focus: 'Video models, preprocessing, and evaluation.', github: 'https://github.com/tarbipyakurel21'},
];

export default function About() {
  return <div className="app-shell marketing-shell about-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <SiteHeader/>
    <main id="main" className="simple-page about-page">
      <section className="container about-hero" aria-labelledby="about-title">
        <div className="about-copy">
          <p className="about-affiliation">University of Southern Mississippi</p>
          <h1 id="about-title">Silicon Peaks.</h1>
          <p>We build DeepTrace: audio and video screening for investigative review.</p>
        </div>
        <div className="about-orbit">
          <Image className="about-everest" src="/mt-everest-cutout.png" alt="Mount Everest at twilight" fill sizes="(max-width: 700px) 100vw, (max-width: 1440px) 58vw, 960px" priority/>
        </div>
      </section>
      <section className="container team-section" aria-labelledby="team-title">
        <header className="team-heading"><h2 id="team-title">The team behind DeepTrace.</h2></header>
        <div className="team-grid">
          {team.map(member => <article className="team-card" key={member.name}>
            <div className="team-avatar" aria-hidden="true"><Image src={member.photo} alt="" fill sizes="120px"/></div>
            <div className="team-card-copy">
              <span>{member.role}</span>
              <h3>{member.name}</h3>
            </div>
            <p>{member.focus}</p>
            <Link href={member.github} target="_blank" rel="noopener noreferrer" aria-label={`${member.name} on GitHub`}>GitHub <span aria-hidden="true">↗</span></Link>
          </article>)}
        </div>
      </section>
      <section className="container about-note" aria-labelledby="about-review-title">
        <h2 id="about-review-title">Human review comes first.</h2>
        <p>DeepTrace supports investigative review. Screening signals guide closer examination; they do not determine a recording’s authenticity.</p>
      </section>
    </main>
    <SiteFooter/>
  </div>;
}
