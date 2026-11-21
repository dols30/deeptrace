import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor} from '@testing-library/react';
import {AuthProvider,useAuth} from './auth';
const {replace,route}=vi.hoisted(()=>({replace:vi.fn(),route:{path:'/'}}));
vi.mock('next/navigation',()=>({usePathname:()=> route.path,useRouter:()=>({replace})}));
function Probe(){const a=useAuth();return <><p>{a.ready?'ready':'waiting'}</p><p>{a.config.enabled?'secured':'disabled'}</p><p>{a.role??'no-role'}</p><p>{a.error}</p><button onClick={()=>a.signIn('dps.employee','secret')}>login</button><button onClick={a.signOut}>logout</button><button onClick={a.expire}>expire</button></>;}
beforeEach(()=>{route.path='/';sessionStorage.clear();history.replaceState({},'','/');});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.clearAllMocks();});
it('loads an explicitly disabled API configuration without creating a token',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({enabled:false})}));
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');expect(screen.getByText('disabled')).toBeTruthy();expect(sessionStorage.getItem('deeptrace_access_token')).toBeNull();
});
it('fails closed when the API configuration cannot be reached',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('offline')));
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');expect(screen.getByText('secured')).toBeTruthy();expect(screen.getByText(/temporarily unavailable/)).toBeTruthy();
});
it('allows the public overview when authentication is enabled',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({enabled:true})}));
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');expect(replace).not.toHaveBeenCalled();
});
it('recovers the supervisor role from an existing token',async()=>{
 const payload=btoa(JSON.stringify({role:'supervisor'})).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
 sessionStorage.setItem('deeptrace_access_token',`header.${payload}.signature`);
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({enabled:true})}));
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');
 expect(screen.getByText('supervisor')).toBeTruthy();
 expect(sessionStorage.getItem('deeptrace_role')).toBe('supervisor');
});
it('submits employee credentials to the backend',async()=>{
 const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({enabled:true,mode:'employee'})}).mockResolvedValueOnce({ok:true,json:async()=>({access_token:'signed-token',role:'analyst'})});vi.stubGlobal('fetch',fetcher);
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');screen.getByText('login').click();
 await waitFor(()=>expect(replace).toHaveBeenCalledWith('/detector'));
 expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining('/v1/auth/login'),expect.objectContaining({method:'POST'}));
 expect(sessionStorage.getItem('deeptrace_access_token')).toBe('signed-token');
});

function jwt(role='analyst', seconds=3600) {
 const payload=btoa(JSON.stringify({role,exp:Math.floor(Date.now()/1000)+seconds})).replaceAll('+','-').replaceAll('/','_').replace(/=+$/,'');
 return `header.${payload}.signature`;
}
it('automatically creates a localhost employee session on a protected page',async()=>{
 route.path='/detector';
 const token=jwt();
 const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({enabled:true,local_auto_login:true})}).mockResolvedValueOnce({ok:true,json:async()=>({access_token:token,role:'analyst'})});
 vi.stubGlobal('fetch',fetcher);
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');
 expect(sessionStorage.getItem('deeptrace_access_token')).toBe(token);
 expect(screen.getByText('analyst')).toBeTruthy();
 expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining('/v1/auth/local-login'),{method:'POST'});
 expect(replace).not.toHaveBeenCalledWith('/signin/');
});
it('keeps a valid manually selected supervisor account',async()=>{
 const token=jwt('supervisor');sessionStorage.setItem('deeptrace_access_token',token);
 const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>({enabled:true,local_auto_login:true})});vi.stubGlobal('fetch',fetcher);
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');
 expect(fetcher).toHaveBeenCalledTimes(1);expect(screen.getByText('supervisor')).toBeTruthy();
});
it('renews an expired automatic local session',async()=>{
 sessionStorage.setItem('deeptrace_access_token',jwt('analyst',-1));
 const token=jwt();
 const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({enabled:true,local_auto_login:true})}).mockResolvedValueOnce({ok:true,json:async()=>({access_token:token,role:'analyst'})});vi.stubGlobal('fetch',fetcher);
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');
 expect(sessionStorage.getItem('deeptrace_access_token')).toBe(token);
});
it('renews a rejected automatic session without returning to the login form',async()=>{
 const token=jwt();
 const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({enabled:true,local_auto_login:true})}).mockResolvedValue({ok:true,json:async()=>({access_token:token,role:'analyst'})});vi.stubGlobal('fetch',fetcher);
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');screen.getByText('expire').click();
 await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(3));
 await screen.findByText('ready');
 expect(sessionStorage.getItem('deeptrace_access_token')).toBe(token);
 expect(replace).not.toHaveBeenCalledWith('/signin/');
});
it('respects explicit signout so another account can be selected',async()=>{
 const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({enabled:true,local_auto_login:true})}).mockResolvedValueOnce({ok:true,json:async()=>({access_token:jwt(),role:'analyst'})});vi.stubGlobal('fetch',fetcher);
 const view=render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');screen.getByText('logout').click();
 expect(sessionStorage.getItem('deeptrace_access_token')).toBeNull();
 view.unmount();
 fetcher.mockResolvedValueOnce({ok:true,json:async()=>({enabled:true,local_auto_login:true})});
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');
 expect(fetcher).toHaveBeenCalledTimes(3);expect(screen.getByText('no-role')).toBeTruthy();
});
it('fails closed if local session issuance fails',async()=>{
 const fetcher=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({enabled:true,local_auto_login:true})}).mockResolvedValueOnce({ok:false,json:async()=>({detail:'unavailable'})});vi.stubGlobal('fetch',fetcher);
 render(<AuthProvider><Probe/></AuthProvider>);await screen.findByText('ready');
 expect(screen.getByText('secured')).toBeTruthy();expect(screen.getByText(/Automatic local sign-in failed/)).toBeTruthy();
 expect(sessionStorage.getItem('deeptrace_access_token')).toBeNull();
});
