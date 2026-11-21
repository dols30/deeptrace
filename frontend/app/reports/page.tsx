'use client';
import {DashboardShell} from '../../components/dashboard-shell';
import {PageFrame} from '../../components/page-frame';
import {SavedReports} from '../../components/saved-reports';

export default function Reports() {
  return <DashboardShell>
    <PageFrame>
      <SavedReports/>
    </PageFrame>
  </DashboardShell>;
}
