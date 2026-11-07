import { createContext, useContext, type ComponentType, type ReactNode } from "react";

// Router-neutral navigation. Pages and components use this instead of a router library,
// so the same source runs under any router that provides an adapter.
export interface AppLinkProps {
  to: string;
  className?: string | undefined;
  activeClassName?: string | undefined;
  exact?: boolean | undefined;
  onClick?: (() => void) | undefined;
  children: ReactNode;
}

export interface RouterAdapter {
  Link: ComponentType<AppLinkProps>;
}

const Ctx = createContext<RouterAdapter | null>(null);
export const RouterAdapterProvider = Ctx.Provider;

export function AppLink(props: AppLinkProps) {
  const a = useContext(Ctx);
  if (!a) return <a href={props.to} className={props.className}>{props.children}</a>;
  return <a.Link {...props} />;
}
