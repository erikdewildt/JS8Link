// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026  JS8Link contributors

import type {
  ButtonHTMLAttributes,
  CSSProperties,
  InputHTMLAttributes,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import {
  cloneElement,
  isValidElement,
  useCallback,
  useId,
  useRef,
  useState,
  type ReactElement,
} from "react";
import { createPortal } from "react-dom";
import { clsx } from "clsx";
import { ArrowDown, CircleHelp } from "lucide-react";

export function Button({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={clsx("button", className)} {...props} />;
}

export function Tooltip({ label, children }: { label: string; children: React.ReactNode }) {
  const tooltipId = `tooltip-${useId().replace(/:/g, "")}`;
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  const [position, setPosition] = useState<CSSProperties>({});

  const show = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setPosition({
      top: rect.top - 8,
      left: rect.right,
      transform: "translate(-100%, -100%)",
    });
    setVisible(true);
  }, []);

  const hide = useCallback(() => setVisible(false), []);

  const target = isValidElement(children)
    ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, {
        "aria-describedby": tooltipId,
      })
    : children;

  return (
    <>
      <span
        ref={triggerRef}
        className="tooltip"
        onPointerEnter={show}
        onPointerLeave={hide}
        onFocus={show}
        onBlur={hide}
      >
        {target}
      </span>
      {visible &&
        createPortal(
          <span className="tooltip-content" id={tooltipId} role="tooltip" style={position}>
            {label}
          </span>,
          document.body,
        )}
    </>
  );
}

export function HelpButton({
  label,
  onClick,
  showText = false,
}: {
  label: string;
  onClick: () => void;
  showText?: boolean;
}) {
  return (
    <Tooltip label={label}>
      <button type="button" className="help-button" aria-label={label} onClick={onClick}>
        <CircleHelp size={15} aria-hidden="true" />
        {showText && <span>{label}</span>}
      </button>
    </Tooltip>
  );
}
export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />;
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className="textarea" {...props} />;
}
export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={clsx("select", className)} {...props} />;
}
export function Card({
  children,
  className,
  style,
}: {
  children: React.ReactNode;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <section className={clsx("card", className)} style={style}>
      {children}
    </section>
  );
}
export function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  return <label className={clsx("label", className)}>{children}</label>;
}
export function Switch({
  checked,
  onCheckedChange,
  disabled = false,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      className={clsx("switch", checked && "checked")}
      onClick={() => onCheckedChange(!checked)}
      disabled={disabled}
    >
      <span className="switch-thumb" />
    </button>
  );
}

export function Tabs({
  value,
  onValueChange,
  children,
}: {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
}) {
  void value;
  void onValueChange;
  return (
    <div className="tabs" data-value={value}>
      {children}
    </div>
  );
}

export function TabsList({ children }: { children: React.ReactNode }) {
  return (
    <div className="tabs-list" role="tablist">
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  active,
  onClick,
  children,
}: {
  value: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  void value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={clsx("tabs-trigger", active && "active")}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function MessageScrollerProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function MessageScroller({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={clsx("message-scroller", className)}>{children}</div>;
}

export function MessageScrollerViewport({
  children,
  onScroll,
  viewportRef,
}: {
  children: React.ReactNode;
  onScroll?: React.UIEventHandler<HTMLDivElement>;
  viewportRef?: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      ref={viewportRef}
      className="message-scroller-viewport"
      role="log"
      tabIndex={0}
      onScroll={onScroll}
    >
      {children}
    </div>
  );
}

export function MessageScrollerContent({ children }: { children: React.ReactNode }) {
  return <div className="message-scroller-content">{children}</div>;
}

export function MessageScrollerItem({
  children,
  messageId,
}: {
  children: React.ReactNode;
  messageId: string;
}) {
  return (
    <div className="message-scroller-item" data-message-id={messageId}>
      {children}
    </div>
  );
}

export function MessageScrollerButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      className="message-scroller-button"
      onClick={onClick}
      aria-label="Latest message"
    >
      <ArrowDown size={15} aria-hidden="true" />
    </button>
  );
}

export function Message({
  children,
  direction,
}: {
  children: React.ReactNode;
  direction: "incoming" | "outgoing";
}) {
  return <div className={clsx("chat-message", `chat-message-${direction}`)}>{children}</div>;
}

export function MessageAvatar({ children }: { children: React.ReactNode }) {
  return <div className="chat-message-avatar">{children}</div>;
}

export function MessageContent({ children }: { children: React.ReactNode }) {
  return <div className="chat-message-content">{children}</div>;
}

export function MessageHeader({ children }: { children: React.ReactNode }) {
  return <div className="chat-message-header">{children}</div>;
}

export function MessageFooter({ children }: { children: React.ReactNode }) {
  return <div className="chat-message-footer">{children}</div>;
}

export function Bubble({ children }: { children: React.ReactNode }) {
  return <div className="chat-bubble">{children}</div>;
}

export function BubbleContent({ children }: { children: React.ReactNode }) {
  return <div className="chat-bubble-content">{children}</div>;
}

export function MessageGroup({ children }: { children: React.ReactNode }) {
  return <div className="chat-message-group">{children}</div>;
}
