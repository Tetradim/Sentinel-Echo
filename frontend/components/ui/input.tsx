import React from 'react';
import { TextInput, StyleSheet } from 'react-native';

export function Input(props: any) {
  return <TextInput style={styles.input} placeholderTextColor="#68779b" {...props} />;
}

const styles = StyleSheet.create({
  input: { backgroundColor: 'rgba(21, 16, 33, 0.82)', color: '#fff', padding: 12, borderRadius: 6, fontSize: 16 },
});
