.. _best-practice:

Best practice
=============

*Short habits that keep a study readable for whoever comes next.*

Write through ``em.write``, always
   One block, one label that says the act in words («Description of SU002»,
   not «fix»). The label is the step of undo and the line of the Log. Do not
   change ``node.raw``: it writes nothing that counts.

One act, one block
   Put in a block what belongs together, and only that. Undo takes the block
   back whole.

Try before you write
   In the console, **Try** runs the code as a proof; outside, ``--dry-run``.

Stamp what you derive
   A picture, a table, a model made from the study carries its stamp:
   ``em.stamp(path, inputs=[…])`` (in a plugin ``ctx.stamp``). Whoever finds
   the file knows what it came from and can check it is still true.

Find nodes by id in code that lasts
   Names are for people and may repeat (``node("SU1")`` with two SU1 raises
   :class:`~s3dgraphy.em.AmbiguousNode`, never returns the first one); ids do
   not change.

Controlled values
   A property that has a vocabulary takes a **concept**, not a free word:
   ``tx.set_property(unit, quale, concept=uri)``; ``em.vocab.search`` gives
   candidates.

Declare what a plugin does
   ``writes = false`` for a command that only reads, the narrowest slots, the
   ``em_api_min`` it really needs.
