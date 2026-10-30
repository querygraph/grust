              throwError(
                "Watermark must be specified in the query using " +
                  "'[Dataset/DataFrame].withWatermark()' for using event-time timeout in a " +
                  "applyInPandasWithState. Event-time timeout not supported without " +
                  "watermark.")(plan)
            }
          }

        case j @ Join(left, right, joinType, condition, _) =>
          if (left.isStreaming && right.isStreaming) {
            joinType match {
              // The behavior for unmatched rows in outer joins with update mode
              // hasn't been defined yet.
              case LeftOuter | RightOuter | FullOuter =>
                if (outputMode != InternalOutputModes.Append) {
                  throwError(s"$joinType join between two streaming DataFrames/Datasets" +
                    s" is not supported in ${outputMode} output mode, only in Append output mode")
                }
              case _: InnerLike | LeftSemi =>
                if (outputMode != InternalOutputModes.Append &&
                    outputMode != InternalOutputModes.Update) {
                  throwError(s"$joinType join between two streaming DataFrames/Datasets" +
                    s" is not supported in ${outputMode} output mode, only in Append and Update " +
                    "output modes")
                }
              case _ => // further unsupported cases will be checked in the next pattern match
            }
          }

          joinType match {
            case _: InnerLike =>
              // no further validations needed

            case FullOuter =>
              if (left.isStreaming && !right.isStreaming) {
                throwError("FullOuter joins with streaming DataFrames/Datasets on the left " +
                  "and a static DataFrame/Dataset on the right is not supported")
              } else if (!left.isStreaming && right.isStreaming) {
                throwError("FullOuter joins with streaming DataFrames/Datasets on the right " +
                  "and a static DataFrame/Dataset on the left is not supported")
              } else if (left.isStreaming && right.isStreaming) {
                checkForStreamStreamJoinWatermark(j)
              }

            case LeftAnti =>
              if (right.isStreaming) {
                throwError(s"$LeftAnti joins with a streaming DataFrame/Dataset " +
                    "on the right are not supported")
              }

            // We support streaming left outer and left semi joins with static on the right always,
            // and with stream on both sides under the appropriate conditions.
            case LeftOuter | LeftSemi =>
              if (!left.isStreaming && right.isStreaming) {
                throwError(s"$joinType join with a streaming DataFrame/Dataset " +
                  "on the right and a static DataFrame/Dataset on the left is not supported")
              } else if (left.isStreaming && right.isStreaming) {
                checkForStreamStreamJoinWatermark(j)
              }

            // We support streaming right outer joins with static on the left always, and with
            // stream on both sides under the appropriate conditions.
            case RightOuter =>
              if (left.isStreaming && !right.isStreaming) {
                throwError("RightOuter join with a streaming DataFrame/Dataset on the left and " +
                    "a static DataFrame/DataSet on the right not supported")
              } else if (left.isStreaming && right.isStreaming) {
                checkForStreamStreamJoinWatermark(j)
              }

            case NaturalJoin(_) | UsingJoin(_, _) =>
              // They should not appear in an analyzed plan.

            case _ =>
              throwError(s"Join type $joinType is not supported with streaming DataFrame/Dataset")
          }

        case d: DeduplicateWithinWatermark if d.isStreaming =>
          // Find any attributes that are associated with an eventTime watermark.
          val watermarkAttributes = d.child.output.collect {
            case a: Attribute if a.metadata.contains(EventTimeWatermark.delayKey) => a
          }
