import React from 'react';

export type TimeLapsePlayerProps = { sources?: string[] };

export const TimeLapsePlayer: React.FC<TimeLapsePlayerProps> = ({ sources = [] }) => {
  return (<div>TimeLapsePlayer placeholder ({sources.length} sources)</div>);
};

export default TimeLapsePlayer;
